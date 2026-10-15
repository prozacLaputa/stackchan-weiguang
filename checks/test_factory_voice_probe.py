"""静音探针的离线边界测试；不读取真实备份或连接网络。"""
import json
import unittest
from unittest.mock import patch,MagicMock

import factory_voice_probe as probe


class FakeMqtt:
    def __init__(self, config):
        self.session = None
        self.sent = []
        self.closed = False
        self.code = 0
        self.messages = []

    def connect(self):
        return self.code

    def subscribe(self):
        return False

    def publish(self, message):
        self.sent.append(message)

    def message(self):
        return self.messages.pop(0)

    def close(self):
        self.closed = True


HELLO = {'type': 'hello', 'session_id': 'synthetic-session', 'transport': 'udp',
         'audio_params': {'format': 'opus', 'sample_rate': 24000, 'channels': 1, 'frame_duration': 60},
         'udp': {'server': 'synthetic.example', 'port': 1234, 'key': 'synthetic-key', 'nonce': 'synthetic-nonce'}}


class SilentProbeTests(unittest.TestCase):
    def test_sentence_is_emitted_before_tts_stop_and_not_logged(self):
        now=[0.0];captions=[]
        messages=[{'type':'tts','state':'start'},
                  {'type':'tts','state':'sentence_start','text':'private-subtitle-fixture'},
                  {'type':'tts','state':'stop'},{'type':'goodbye'}]
        client=MagicMock();client.session='synthetic';client.socket.pending.return_value=0
        client.message.side_effect=lambda:messages.pop(0)
        def select(read,write,error,timeout):
            now[0]+=timeout
            return ([client.socket] if messages else [],[],[])
        hello={'udp':{'key':'00'*16,'nonce':'01'+'00'*15,'port':1234,'server':'unused.invalid'}}
        report={'events':[],'capability_requests':['tools/list']}
        with patch.object(probe.socket,'socket'),patch.object(probe.select,'select',side_effect=select), \
             patch.object(probe.time,'monotonic',side_effect=lambda:now[0]), \
             patch.object(probe.time,'sleep',side_effect=lambda t:now.__setitem__(0,now[0]+t)):
            probe.text_probe(client,hello,report,'listen-first',input_packets=[b'\xf8\xff\xfe'],
                             subtitle_sink=lambda text:captions.append((text,report['tts_stopped'])))
        self.assertEqual(captions,[('private-subtitle-fixture',False)])
        self.assertNotIn('private-subtitle-fixture',json.dumps(report))
        self.assertTrue(report['tts_stopped'])

    def test_receive_loop_exits_on_cloud_close_and_silence(self):
        for messages,code in (([{'type':'goodbye'}],'service_closed_without_reply'),
                              ([], 'recognition_timeout'),
                              ([{'type':'stt','text':'private-transcript-fixture'}],'first_audio_timeout')):
            now=[0.0];pending=list(messages)
            client=MagicMock();client.session='synthetic';client.socket.pending.return_value=0
            client.message.side_effect=lambda:pending.pop(0)
            def select(read,write,error,timeout):
                now[0]+=timeout
                return ([client.socket] if pending else [],[],[])
            hello={'udp':{'key':'00'*16,'nonce':'01'+'00'*15,'port':1234,'server':'unused.invalid'}}
            report={'events':[],'capability_requests':['tools/list']}
            with patch.object(probe.socket,'socket'),patch.object(probe.select,'select',side_effect=select), \
                 patch.object(probe.time,'monotonic',side_effect=lambda:now[0]), \
                 patch.object(probe.time,'sleep',side_effect=lambda t:now.__setitem__(0,now[0]+t)):
                with self.assertRaisesRegex(ValueError,code):
                    probe.text_probe(client,hello,report,'listen-first',input_packets=[b'\xf8\xff\xfe'])
            self.assertLess(now[0],22)
            self.assertEqual(report['audio_packets'],0)
            self.assertNotIn('private-transcript-fixture',json.dumps(report))

    def test_closed_service_without_reply_fails_immediately(self):
        for event,code in (({'type':'goodbye'},'service_closed_without_reply'),
                           ({'type':'error','text':'private error'},'service_error')):
            with self.assertRaisesRegex(ValueError,code):
                probe.observe_response(event,{},0)
    def test_normal_goodbye_after_tts_stop_still_drains_audio(self):
        report={}
        probe.observe_response({'type':'tts','state':'start'},report,0)
        probe.observe_response({'type':'tts','state':'stop'},report,2)
        probe.observe_response({'type':'goodbye'},report,2.1)
        self.assertTrue(report['tts_stopped'])
    def test_response_wait_is_bounded_per_stage(self):
        with self.assertRaisesRegex(ValueError,'recognition_timeout'):
            probe.check_response_wait({},12.1,None)
        with self.assertRaisesRegex(ValueError,'first_audio_timeout'):
            probe.check_response_wait({'stt_received':True,'stt_seconds':2},22.1,None)
        with self.assertRaisesRegex(ValueError,'audio_stalled'):
            probe.check_response_wait({'audio_packets':2},20,11)
        probe.check_response_wait({'audio_packets':2},29,28.9)
        probe.check_response_wait({'tts_stopped':True},29,10)
    def test_ingress_leaves_time_for_control_and_last_audio(self):
        now=[0];events=[]
        def sleep(seconds):now[0]+=seconds
        with patch.object(probe.time,'monotonic',side_effect=lambda:now[0]),patch.object(probe.time,'sleep',side_effect=sleep):
            probe.send_speech_packets(lambda i,p:events.append(('packet',now[0])),[b'a',b'b'],0.06,{})
        self.assertGreaterEqual(events[0][1],0.18)
        self.assertGreaterEqual(now[0]-events[-1][1],0.18)

    def test_udp_reordering_and_duplicates_do_not_repeat_audio(self):
        emitted=[];report={};queue=probe.OrderedAudioPackets(lambda n,p:emitted.append(n),report)
        queue.add(10,b'a',0);queue.add(12,b'c',0.04);queue.add(11,b'b',0.06)
        self.assertEqual(emitted,[])
        queue.drain(0.13);self.assertEqual(emitted,[10,11,12])
        queue.add(11,b'b',0.14);self.assertEqual(emitted,[10,11,12])
        self.assertEqual(report['reordered_audio_packets'],1)
    def test_real_gap_still_stops_instead_of_playing_wrong_sequence(self):
        emitted=[];report={};queue=probe.OrderedAudioPackets(lambda n,p:emitted.append(n),report)
        queue.add(1,b'a',0);queue.add(3,b'c',0.01);queue.drain(0.13)
        self.assertEqual(emitted,[1])
        with self.assertRaisesRegex(ValueError,'audio_packet_gap'):queue.drain(0.4)
        self.assertEqual(report['missing_audio_packets'],1)
        self.assertEqual(emitted,[1])
    def test_final_drain_and_bounded_queue(self):
        emitted=[];queue=probe.OrderedAudioPackets(lambda n,p:emitted.append(n),{})
        queue.add(1,b'a',0);queue.drain(0.02,final=True);self.assertEqual(emitted,[1])
        queue=probe.OrderedAudioPackets(lambda *_:None,{})
        for n in range(32):queue.add(n,b'a',0)
        with self.assertRaises(ValueError):queue.add(33,b'b',0)
    def run_fake(self, client, **kwargs):
        with patch.object(probe, 'read_identity', return_value={'mqtt': {}}), \
             patch.object(probe, 'summary', return_value={'bound_device_matches_mqtt_client': True}), \
             patch.object(probe, 'Mqtt', return_value=client):
            return probe.probe(**kwargs)

    def test_rejected_auth_does_not_activate_or_publish(self):
        client = FakeMqtt({}); client.code = 5
        result = self.run_fake(client)
        self.assertFalse(result['ok'])
        self.assertFalse(result['activation_attempted'])
        self.assertEqual(client.sent, [])
        self.assertTrue(client.closed)

    def test_activation_stops_without_following_it(self):
        client = FakeMqtt({}); client.messages = [{'type': 'activation', 'code': 'synthetic-code'}]
        result = self.run_fake(client, with_text=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['result'], 'activation_required_stopped')
        self.assertEqual([message['type'] for message in client.sent], ['hello'])
        self.assertNotIn('synthetic-code', json.dumps(result))

    def test_hello_is_not_a_claim_that_voice_works(self):
        client = FakeMqtt({}); client.messages = [HELLO]
        result = self.run_fake(client)
        self.assertTrue(result['ok'])
        self.assertNotIn('text_audio_passed', result)
        self.assertFalse(result['audio_output_created'])
        self.assertFalse(result['microphone_opened'])
        for secret in ('synthetic-session', 'synthetic-key', 'synthetic-nonce'):
            self.assertNotIn(secret, json.dumps(result))
        self.assertTrue(client.closed)

    def test_text_failure_clears_handshake_success(self):
        client = FakeMqtt({}); client.messages = [HELLO]
        with patch.object(probe, 'text_probe', side_effect=ValueError('synthetic-private-value')):
            result = self.run_fake(client, with_text=True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error_type'], 'ValueError')
        self.assertNotIn('synthetic-private-value', json.dumps(result))

    def test_no_tools_are_exposed_or_executed(self):
        client = FakeMqtt({}); report = {}
        for method in ('initialize', 'tools/list', 'tools/call', 'arbitrary'):
            probe.handle_capabilities(client, {'type': 'mcp', 'payload': {'jsonrpc': '2.0', 'id': 1, 'method': method}}, report)
        self.assertEqual(client.sent[1]['payload']['result']['tools'], [])
        self.assertEqual(client.sent[2]['payload']['error']['code'], -32601)
        self.assertEqual(client.sent[3]['payload']['error']['code'], -32601)


if __name__ == '__main__':
    unittest.main()
