import sys
import base64
import json
import unittest
from contextlib import ExitStack
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'bridge'))
from voice_commands import parse_voice_command
import factory_voice_client as client


class VoiceCommandsTests(unittest.TestCase):
    def test_explicit_timer_commands(self):
        for text in ('帮我开始一个25分钟番茄钟。','微光，请帮我开始一个二十五分钟的番茄钟','开始番茄钟','帮我开始1个25分钟的番茄钟。'):
            self.assertEqual(parse_voice_command(text),{'kind':'focus','operation':'start','minutes':25})
        self.assertEqual(parse_voice_command('请启动十五分钟专注计时')['minutes'],15)
        self.assertEqual(parse_voice_command('暂停一下番茄钟'),{'kind':'focus','operation':'pause'})
        self.assertEqual(parse_voice_command('暂停一下番茄中。'),{'kind':'focus','operation':'pause'})
        self.assertEqual(parse_voice_command('继续番茄钟'),{'kind':'focus','operation':'resume'})
        self.assertEqual(parse_voice_command('结束番茄钟'),{'kind':'focus','operation':'stop'})
    def test_notes_preserve_content_and_obey_device_limit(self):
        self.assertEqual(parse_voice_command('记个便签：下班带充电器。'),{'kind':'note','text':'下班带充电器'})
        self.assertEqual(parse_voice_command('帮我写个便签，明天不要忘了带书'),{'kind':'note','text':'明天不要忘了带书'})
        self.assertEqual(parse_voice_command('记个便签下班带充电器'),{'kind':'note','text':'下班带充电器'})
        self.assertEqual(parse_voice_command('寄个便签，下班带充电器。'),{'kind':'note','text':'下班带充电器'})
        self.assertEqual(parse_voice_command('记个便签：'+'长'*33),{'kind':'help','code':'note_length'})
    def test_unsupported_duration_is_explained_without_starting(self):
        self.assertEqual(parse_voice_command('开始五分钟番茄钟'),{'kind':'help','code':'focus_duration'})
    def test_chat_quotes_negation_and_compound_requests_never_execute(self):
        for text in ('不要开始25分钟番茄钟','我想知道怎么开始25分钟番茄钟','开始番茄钟是什么意思',
                     '如果我说开始25分钟番茄钟你会怎样','开始25分钟番茄钟好吗','开始番茄钟？',
                     '开始番茄钟然后删掉文件','他说“开始番茄钟”','暂停一下','我想记个便签','好的，已经开始番茄钟'):
            with self.subTest(text=text):self.assertIsNone(parse_voice_command(text))

    def worker(self,transcription,*,enabled=True):
        # 固定的 Opus 静音包，不依赖本机历史探针留下的音频文件。
        packets=[bytes.fromhex('f8fffe')]*2
        chunks=[];events=[]
        def probe(_connection,_hello,report,_mode,_input,packet_sink,**options):
            packet_sink(1,packets[0])
            options['subtitle_sink']('好的，我帮你开始。')
            self.assertEqual(chunks,[] if enabled else [bytes(chunks[0])])
            if transcription is not None:options['transcript_sink'](transcription)
            packet_sink(2,packets[1]);report['tts_stopped']=True
        request={'audio_pcm16':base64.b64encode(b'\0\0'*16000).decode(),'sample_rate':16000,
                 'local_commands':enabled,'stream':True,'transcript_events':True,'subtitle_events':True,
                 'libopus':'/opt/homebrew/lib/libopus.dylib'}
        with ExitStack() as stack:
            stack.enter_context(patch.object(client,'microphone_packets',return_value=packets))
            stack.enter_context(patch.object(client,'read_identity',return_value={'mqtt':{}}))
            stack.enter_context(patch.object(client,'summary',return_value={'bound_device_matches_mqtt_client':True}))
            stack.enter_context(patch.object(client,'handle_capabilities'))
            connection=stack.enter_context(patch.object(client,'Mqtt')).return_value
            connection.connect.return_value=0;connection.socket=None
            connection.message.return_value={'type':'hello','transport':'udp','session_id':'fixture','audio_params':{'format':'opus','channels':1}}
            stack.enter_context(patch.object(client,'text_probe',side_effect=probe))
            pcm,report=client.run_exclusive(request,pcm_sink=chunks.append,event_sink=events.append)
        return pcm,report,chunks,events

    def test_real_worker_intercepts_user_instruction_before_any_audio_or_reply(self):
        pcm,report,chunks,events=self.worker('帮我开始一个25分钟番茄钟。')
        self.assertEqual(pcm,b'');self.assertEqual(chunks,[])
        self.assertTrue(report['local_command']);self.assertFalse(report['streaming'])
        self.assertEqual([x['event'] for x in events],['transcript','local_command'])
        self.assertEqual(events[-1]['command'],{'kind':'focus','operation':'start','minutes':25})
        self.assertNotIn('25分钟',json.dumps(report,ensure_ascii=False))

    def test_ordinary_chat_releases_buffer_and_stays_streaming(self):
        pcm,report,chunks,events=self.worker('今天心情不错。')
        self.assertEqual(b''.join(chunks),pcm);self.assertTrue(report['streaming'])
        self.assertFalse(any(x['event']=='local_command' for x in events))

    def test_disabled_control_does_not_execute_commands(self):
        pcm,report,chunks,events=self.worker('开始25分钟番茄钟',enabled=False)
        self.assertTrue(chunks);self.assertFalse(any(x['event']=='local_command' for x in events))

    def test_missing_transcript_cannot_leak_model_reply(self):
        with self.assertRaisesRegex(ValueError,'recognition_timeout'):self.worker(None)

    def test_no_local_commands_from_text_or_without_transcript_channel(self):
        for request in ({'text':'开始番茄钟','local_commands':True},
                        {'audio_pcm16':base64.b64encode(b'\0\0'*16000).decode(),'sample_rate':16000,'local_commands':True}):
            with patch.object(client,'read_identity') as identity:
                with self.assertRaisesRegex(ValueError,'invalid_stream_options'):client.run_exclusive(request)
                identity.assert_not_called()


if __name__=='__main__':unittest.main()
