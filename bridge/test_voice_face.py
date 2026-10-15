import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from control import ControlServer, VoiceMailbox, request, validate_request, parse_device
from runtime import Bridge
from test_runtime import FakeSerial, task


class VoiceLink(FakeSerial):
    def write(self,data):
        self.packets.append(data)
        self.ack=b'VOICE_ACK\t'+data.split(b'\t')[1]+b'\n'
    def readline(self):return self.ack


class VoiceFaceTests(unittest.TestCase):
    def test_validation_and_freshness(self):
        box=VoiceMailbox()
        self.assertEqual(box.current(),-1)
        for level in (True,4,-2,'1'):
            with self.assertRaises(ValueError):validate_request(dict(action='voice',level=level,at=time.time()))
        for stamp in (float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):validate_request(dict(action='voice',level=1,at=stamp))
        self.assertFalse(box.accept(dict(action='voice',level=2,at=time.time()-2)))
        self.assertFalse(box.accept(dict(action='voice',level=2,at=time.time()+2)))
        self.assertTrue(box.accept(dict(action='voice',level=2,at=time.time())))
        self.assertEqual(box.current(),2)
        with patch('control.time.monotonic',return_value=box.expires+.001):self.assertEqual(box.current(),-1)
        box.clear();self.assertEqual(box.current(),-1)

    def test_socket_coalesces_without_filling_settings_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            server=ControlServer(folder).start()
            try:
                for level in (0,1,2,3,0,-1):
                    self.assertTrue(request(folder,dict(action='voice',level=level,at=time.time()))['ok'])
                self.assertIsNone(server.take());self.assertEqual(server.voice.current(),-1)
                self.assertFalse(request(folder,dict(action='voice',level=3,at=time.time()-10))['ok'])
            finally:server.close()

    def test_forward_latest_ack_clear_disconnect_and_legacy(self):
        with tempfile.TemporaryDirectory() as folder:
            server=ControlServer(folder);link=VoiceLink()
            bridge=Bridge(SimpleNamespace(snapshot=lambda:[task()]),Path(folder),control=server)
            bridge.link=link;bridge.baseline_pending=False;bridge.device={'firmware':'0.47'}
            for level in (1,2,3):server.voice.accept(dict(action='voice',level=level,at=time.time()))
            bridge.maintain_voice();self.assertTrue(link.packets[-1].endswith(b'\t3\n'))
            self.assertEqual(bridge.voice_acks,1)
            server.voice.clear();bridge.maintain_voice();self.assertTrue(link.packets[-1].endswith(b'\t-1\n'))
            self.assertFalse(bridge.voice_active)
            count=len(link.packets);bridge.maintain_voice();self.assertEqual(len(link.packets),count)
            server.voice.accept(dict(action='voice',level=3,at=time.time()))
            bridge.device={'firmware':'0.46'};bridge.maintain_voice();self.assertEqual(len(link.packets),count)
            bridge.disconnect();self.assertEqual(server.voice.current(),-1)

    def test_v47_retains_all_settings(self):
        raw=b'DEVICE\t7\t0.47\t100\t1\thome\t0\t70\t1\t1\t1\t0\t40\t0\t0\t0\tready\tnone\t0\t1\t0\t0\tnone\tnone\t0\t1\t1\t1\t1\t1\t1\n'
        device=parse_device(raw,7)
        self.assertEqual(device['skin'],1);self.assertEqual(device['focus_motion'],1)
        self.assertEqual(device['wait_motion'],0);self.assertEqual(device['done_motion'],0)

if __name__=='__main__':unittest.main()
