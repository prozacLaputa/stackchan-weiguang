"""录音协议边界：合成内存数据，无麦克风、无网络、无播放。"""
import base64
from pathlib import Path
import subprocess
import sys
import unittest
import ctypes.util
import shutil
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'bridge'))
import factory_voice_client as client

class MicrophoneTests(unittest.TestCase):
    def request(self,pcm=b'\0\0'*16000,rate=16000):
        return {'audio_pcm16':base64.b64encode(pcm).decode(), 'sample_rate':rate}
    def test_bounds_and_mutual_exclusion_before_identity_or_network(self):
        good=self.request()
        bad=[{}, {'audio_pcm16':'../../private.wav','sample_rate':16000},
             {**good,'text':'ambiguous'}, {**good,'sample_rate':True},
             {**good,'sample_rate':16000.0}, {**good,'sample_rate':96000},
             self.request(b'\0'), self.request(b'\0\0'*100),
             self.request(b'\0\0'*(16000*30+1)), {**good,'audio_pcm16':'A'*3840004}]
        for request in bad:
            with self.subTest(keys=list(request)),patch.object(client,'read_identity') as identity,patch.object(client,'microphone_packets') as encode:
                with self.assertRaises(ValueError):client.run_exclusive(request)
                identity.assert_not_called();encode.assert_not_called()
        text,pcm,rate=client.input_payload(good)
        self.assertIsNone(text);self.assertEqual(len(pcm),32000);self.assertEqual(rate,16000)
    def test_transcript_is_opt_in_one_time_and_bounded(self):
        events=[];emit=client.TranscriptEmitter(events.append)
        for value in (None,{},'\0','x'*2001):emit(value)
        self.assertEqual(events,[])
        emit('你好\0');emit('duplicate')
        self.assertEqual(events,[{'event':'transcript','text':'你好'}])
        disabled=client.TranscriptEmitter(None);disabled('private');self.assertFalse(disabled.sent)
    def test_pcm_encoding_uses_pipes_and_preserves_30_second_limit(self):
        for rate in (8000,16000,24000,44100,48000):
            with self.subTest(rate=rate):
                pcm=b'\0\0'*(rate*30)
                with patch.object(client.tempfile,'TemporaryDirectory',side_effect=AssertionError('microphone must not touch temp files')):
                    packets=client.microphone_packets(pcm,rate,(shutil.which('ffmpeg') or 'ffmpeg'))
                self.assertTrue(500<=len(packets)<=501)
    def test_cancelled_encoder_is_killed(self):
        with patch.object(client.subprocess,'Popen') as process:
            child=process.return_value;child.communicate.side_effect=InterruptedError();child.poll.return_value=None
            with self.assertRaises(InterruptedError):client.microphone_packets(b'\0'*32000,16000,'fixture')
            child.kill.assert_called_once();child.wait.assert_called_once()

if __name__=='__main__':unittest.main()
