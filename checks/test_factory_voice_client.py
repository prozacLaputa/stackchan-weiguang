"""仅使用固定生成输入：Opus解码、丢包拒绝与请求边界，无网络／播放。"""
import json
import math
from array import array
from pathlib import Path
import sys
import tempfile
import ctypes.util
import shutil
import unittest
from contextlib import ExitStack
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
TEST_OPUS=next((str(p) for p in (Path('/opt/homebrew/lib/libopus.dylib'),Path('/usr/local/lib/libopus.dylib')) if p.is_file()),ctypes.util.find_library('opus') or 'libopus.dylib')
sys.path.insert(0,str(ROOT/'bridge'))
import factory_voice_client as client
from factory_voice_probe import OrderedAudioPackets


class ClientTests(unittest.TestCase):
    def notice_request(self,reply,received,events,*,complete=True,expected=True):
        """Exercise the real worker boundary; only the remote service and input encoding are fixtures."""
        line='「界面优化」这一轮完成了，可以看看结果。'
        packets=client.opus_packets((ROOT/'.runtime/fixtures/synthetic-input.ogg').read_bytes())
        def probe(_connection,_hello,report,_mode,_input,packet_sink,**options):
            # Audio can precede the final subtitle. Nothing may escape before full verification.
            packet_sink(1,packets[0])
            for part in reply:options['subtitle_sink'](part)
            packet_sink(2,packets[1])
            report['tts_stopped']=complete
        request={'text':'请只读下面的任务提醒：'+line,'stream':True,'subtitle_events':True,
                 'libopus':TEST_OPUS}
        if expected:request['expected_speech']=line
        with ExitStack() as stack:
            stack.enter_context(patch.object(client,'command'))
            stack.enter_context(patch.object(client.Path,'read_bytes',return_value=b'fixture'))
            stack.enter_context(patch.object(client,'opus_packets',return_value=packets))
            stack.enter_context(patch.object(client,'read_identity',return_value={'mqtt':{}}))
            stack.enter_context(patch.object(client,'summary',return_value={'bound_device_matches_mqtt_client':True}))
            stack.enter_context(patch.object(client,'handle_capabilities'))
            connection=stack.enter_context(patch.object(client,'Mqtt')).return_value
            connection.connect.return_value=0;connection.socket=None
            connection.message.return_value={'type':'hello','transport':'udp','session_id':'fixture','audio_params':{'format':'opus','channels':1}}
            stack.enter_context(patch.object(client,'text_probe',side_effect=probe))
            return client.run_exclusive(request,pcm_sink=received.append,event_sink=events.append)

    def test_task_notice_acknowledgement_never_reaches_audio_output(self):
        received=[];events=[]
        with self.assertRaisesRegex(ValueError,'notice_text_mismatch'):
            self.notice_request(['好的，收到了。'],received,events)
        self.assertEqual(received,[]);self.assertEqual(events,[])

    def test_task_notice_accepts_only_complete_exact_subtitles_and_buffers_audio(self):
        received=[];events=[]
        pcm,report=self.notice_request(['界面优化这一轮完成了，','可以看看结果。'],received,events)
        self.assertGreater(len(pcm),0);self.assertEqual(received,[]);self.assertEqual(events,[])
        self.assertTrue(report['notice_text_verified']);self.assertFalse(report['streaming'])
        self.assertNotIn('界面优化',json.dumps(report,ensure_ascii=False))

    def test_task_notice_rejects_extra_missing_or_changed_words(self):
        for reply in ([],['请严格复述冒号后面的原文，'],['界面优化这一轮完成了'],['文档整理这一轮完成了，可以看看结果。'],
                      ['界面优化这一轮完成了，可以看看结果。','好的，收到了。']):
            with self.subTest(reply=reply):
                received=[];events=[]
                with self.assertRaisesRegex(ValueError,'notice_text_mismatch'):
                    self.notice_request(reply,received,events)
                self.assertEqual(received,[])
        with self.assertRaisesRegex(ValueError,'reply_incomplete'):
            self.notice_request(['界面优化这一轮完成了，可以看看结果。'],[],[],complete=False)

    def test_chat_keeps_streaming_without_notice_validation(self):
        received=[];events=[]
        pcm,report=self.notice_request(['好的，收到了。'],received,events,expected=False)
        self.assertEqual(b''.join(received),pcm);self.assertTrue(report['streaming'])
        self.assertEqual(events[0]['text'],'好的，收到了。')

    def test_invalid_notice_expectation_never_generates_or_connects(self):
        for expected in ('','。',True,42,'a'*121,'hello\nworld',None):
            with patch.object(client,'command') as command,patch.object(client,'read_identity') as identity:
                with self.assertRaisesRegex(ValueError,'invalid_expected_speech'):
                    client.run_exclusive({'text':'测试','expected_speech':expected})
                command.assert_not_called();identity.assert_not_called()

    def test_subtitle_emitter_is_opt_in_bounded_and_preserves_real_repetition(self):
        events=[];emitter=client.SubtitleEmitter(events.append)
        for text in (None,{},'', '\0\x01'):emitter(text)
        self.assertEqual(events,[])
        emitter('你好\0');emitter('你好')
        self.assertEqual([x['sequence'] for x in events],[1,2])
        self.assertEqual([x['text'] for x in events],['你好','你好'])
        emitter('a'*2001);self.assertEqual(len(events),2)
        for _ in range(70):emitter('短句')
        self.assertEqual(len(events),64)
        disabled=client.SubtitleEmitter(None);disabled('private fixture')
        self.assertEqual(disabled.count,0)
    def test_factory_session_is_exclusive_and_released_after_cancel(self):
        with tempfile.TemporaryDirectory() as folder:
            lock=Path(folder)/'lease'
            with self.assertRaises(InterruptedError):
                with client.factory_session(lock,timeout=0):
                    with self.assertRaisesRegex(ValueError,'previous_session_busy'):
                        with client.factory_session(lock,timeout=0):pass
                    raise InterruptedError('synthetic cancel')
            with client.factory_session(lock,timeout=0):pass
            self.assertEqual(lock.stat().st_mode & 0o777,0o600)
    def test_short_inputs_use_reliable_pacing_without_slowing_long_inputs(self):
        self.assertEqual(client.input_upload_interval_ms(10),60)
        self.assertEqual(client.input_upload_interval_ms(30),60)
        self.assertEqual(client.input_upload_interval_ms(62),15)
        self.assertEqual(client.input_upload_interval_ms(10,15),15)
    def test_ordered_stream_conceals_one_missing_packet_then_continues(self):
        packets=client.opus_packets((ROOT/'.runtime/fixtures/synthetic-input.ogg').read_bytes())
        chunks=[];report={};decoder=client.OpusDecoder(TEST_OPUS,pcm_sink=chunks.append)
        try:
            queue=OrderedAudioPackets(decoder.add,report,gap_sink=decoder.conceal)
            queue.add(1,packets[0],0);queue.add(3,packets[2],0.02);queue.drain(0.13)
            self.assertEqual(len(chunks),1)
            queue.drain(0.4)
            self.assertEqual(len(chunks),3)
            self.assertEqual(len(decoder.output),3*2880*4)
            self.assertEqual(report['concealed_audio_packets'],1)
            queue.add(2,packets[1],0.41);self.assertEqual(len(chunks),3)
            queue.add(4,packets[3],0.42);self.assertEqual(len(chunks),4)
            self.assertTrue(all(math.isfinite(v) and abs(v)<=1 for v in array('f',decoder.output)))
        finally:decoder.close()
    def test_concealment_rejects_large_or_repeated_loss(self):
        packets=client.opus_packets((ROOT/'.runtime/fixtures/synthetic-input.ogg').read_bytes())
        decoder=client.OpusDecoder(TEST_OPUS)
        try:
            with self.assertRaisesRegex(ValueError,'audio_packet_gap'):decoder.conceal(1)
            decoder.add(1,packets[0]);size=len(decoder.output)
            with self.assertRaisesRegex(ValueError,'audio_packet_gap'):decoder.conceal(3)
            self.assertEqual(len(decoder.output),size)
            for _ in range(3):decoder.conceal(2)
            with self.assertRaisesRegex(ValueError,'audio_packet_gap'):decoder.conceal(1)
        finally:decoder.close()
    def test_decoder_emits_each_packet_before_reply_completes(self):
        packets=client.opus_packets((ROOT/'.runtime/fixtures/synthetic-input.ogg').read_bytes())
        chunks=[]
        decoder=client.OpusDecoder(TEST_OPUS,pcm_sink=chunks.append)
        try:
            decoder.add(1,packets[0]);self.assertEqual(len(chunks),1)
            self.assertEqual(chunks[0],bytes(decoder.output))
            decoder.add(1,packets[0]);self.assertEqual(len(chunks),1)
            decoder.add(2,packets[1]);self.assertEqual(len(chunks),2)
            with self.assertRaises(ValueError):decoder.add(4,packets[2])
            self.assertEqual(len(chunks),2)
        finally:decoder.close()
    def test_invalid_text_never_generates_or_connects(self):
        for text in ('', 'a'*121,'hello\nworld',42):
            with patch.object(client,'command') as command,patch.object(client,'read_identity') as identity:
                with self.assertRaises(ValueError):client.run({'text':text})
                command.assert_not_called();identity.assert_not_called()
    def test_truncated_ogg_is_rejected(self):
        for data in (b'',b'OggS\0',b'OggS\0'+b'\0'*21+b'\x01'):
            with self.assertRaises(ValueError):client.opus_packets(data)
    def test_decode_generated_fixture_and_reject_loss(self):
        packets=client.opus_packets((ROOT/'.runtime/fixtures/synthetic-input.ogg').read_bytes())
        decoder=client.OpusDecoder(TEST_OPUS)
        try:
            decoder.add(1,packets[0]);size=len(decoder.output)
            self.assertEqual(size,2880*4)
            decoder.add(1,packets[0]);self.assertEqual(len(decoder.output),size)
            self.assertEqual(decoder.duplicates,1)
            with self.assertRaises(ValueError):decoder.add(3,packets[1])
        finally:decoder.close()
    def test_cancelled_generation_cleans_child(self):
        with patch.object(client.subprocess,'Popen') as process:
            child=process.return_value;child.wait.side_effect=[InterruptedError(),0];child.poll.return_value=None
            with self.assertRaises(InterruptedError):client.command(['synthetic'],1)
            child.kill.assert_called_once()
    def test_invalid_sound_options_do_not_generate_or_connect(self):
        for options in ({'rate':0},{'rate':float('nan')},{'pitch':3},{'pitch':True},{'rate':'fast'}):
            with patch.object(client,'command') as command,patch.object(client,'read_identity') as identity:
                with self.assertRaises(ValueError):client.run({'text':'测试',**options})
                command.assert_not_called();identity.assert_not_called()
    def test_original_sound_is_byte_exact(self):
        pcm=array('f',[0,0.3,-0.25]).tobytes()
        with patch.object(client.subprocess,'Popen') as process:
            self.assertEqual(client.shape_audio(pcm,'unused',1,0),pcm)
            process.assert_not_called()
    def test_invalid_stream_options_do_not_generate_or_connect(self):
        for options in ({'stream':'yes'},{'stream':1},{'upload_interval_ms':0},{'upload_interval_ms':True},{'upload_interval_ms':15.0},
                        {'input_guard_ms':True},{'input_guard_ms':-1},{'input_guard_ms':'180'}, {'subtitle_events':'true'}):
            with patch.object(client,'command') as command,patch.object(client,'read_identity') as identity:
                with self.assertRaisesRegex(ValueError,'invalid_stream_options'):client.run({'text':'测试',**options})
                command.assert_not_called();identity.assert_not_called()
    def test_speed_and_pitch_are_independent_without_audio_output(self):
        pcm=array('f',(0.2*math.sin(2*math.pi*440*i/48000) for i in range(48000))).tobytes()
        for rate,pitch in ((0.8,0),(1.25,0),(1,2),(1,-2),(0.9,-1),(1.1,1)):
            out=client.shape_audio(pcm,(shutil.which('ffmpeg') or 'ffmpeg'),rate,pitch)
            samples=array('f');samples.frombytes(out)
            self.assertAlmostEqual(len(samples)/48000,1/rate,delta=0.06)
            middle=samples[len(samples)//5:len(samples)*4//5]
            crossings=sum(a<=0<b for a,b in zip(middle,middle[1:]))
            frequency=crossings/(len(middle)/48000)
            self.assertAlmostEqual(frequency,440*2**(pitch/12),delta=6)
            self.assertTrue(all(math.isfinite(x) and abs(x)<=1 for x in samples))
    def test_sound_processing_cancel_kills_child(self):
        with patch.object(client.subprocess,'Popen') as process:
            child=process.return_value;child.communicate.side_effect=InterruptedError();child.poll.return_value=None
            with self.assertRaises(InterruptedError):client.shape_audio(b'0000','unused',0.9,0)
            child.kill.assert_called_once()
    def test_sound_processing_failure_is_not_a_playable_reply(self):
        with patch.object(client.subprocess,'Popen') as process:
            child=process.return_value;child.communicate.return_value=(b'0000',None);child.returncode=1;child.poll.return_value=1
            with self.assertRaisesRegex(ValueError,'sound_processing_failed'):client.shape_audio(b'0000','unused',0.9,0)


if __name__=='__main__':unittest.main()
