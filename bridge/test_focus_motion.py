from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from control import parse_device, Command, ControlServer
from runtime import Bridge
from test_skin import v37

class FocusMotionTests(unittest.TestCase):
    def test_new_reply_and_old_compatibility(self):
        raw=v37().strip().replace(b'0.37',b'0.41')+b'\t1'
        d=parse_device(raw,7);self.assertEqual(d['focus_motion'],1);self.assertEqual(d['skin'],1)
        for version in (b'0.41',b'0.42',b'0.43',b'0.44'):
            current=raw.replace(b'0.41',version).replace(b'\thome\t',b'\tfocus\t')
            with self.subTest(version=version):
                parsed=parse_device(current,7)
                self.assertEqual(parsed['firmware'],version.decode())
                self.assertEqual(parsed['focus_motion'],1)
        for bad in (raw[:-1]+b'2', raw.rsplit(b'\t',1)[0], raw.replace(b'0.41',b'0.40')):
            with self.assertRaises(ValueError):parse_device(bad,7)

    def test_patch_wire_and_previous_preferences_preserved(self):
        class Link:
            port='test'
            def write(self,raw):self.fields=raw.decode().strip().split('\t')
            def readline(self):return v37().strip().replace(b'0.37',b'0.41').replace(b'DEVICE\t7\t',f'DEVICE\t{self.fields[1]}\t'.encode())+b'\t0'
        with tempfile.TemporaryDirectory() as directory:
            hub=ControlServer(Path(directory));bridge=Bridge(SimpleNamespace(),directory,control=hub)
            link=Link();bridge.link=link;bridge.link_transport='ble';bridge.baseline_pending=False;bridge.device={'firmware':'0.41'}
            command=Command({'action':'configure','changes':{'focus_motion':0}});hub.queue.put(command);bridge.maintain_device()
            self.assertTrue(command.result['ok']);self.assertEqual(link.fields[2:],['-']*10+['0'])
            self.assertEqual(bridge.device['focus_motion'],0)
            bridge.device={'firmware':'0.40'};command=Command({'action':'configure','changes':{'focus_motion':1}});hub.queue.put(command);bridge.maintain_device()
            self.assertEqual(command.result['error'],'firmware_update_required')
