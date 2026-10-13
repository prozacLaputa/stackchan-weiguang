import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from runtime import Bridge
from monitor import sync_packet
from ble_link import BleLink,BleError
import service

class FakeBle:
    def __init__(self,*args):self.port='ble:0123456789ab';self.closed=False;self.fail=False;self.packet=None
    def open(self):pass
    def write(self,data):
        if self.fail:raise BleError('ble_disconnected')
        self.packet=data
    def readline(self):return b'ACK\t'+self.packet.split(b'\t')[1]+b'\n'
    def close(self):self.closed=True

class WirelessTests(unittest.TestCase):
    def test_packet_metadata_and_utf8(self):
        task=dict(id='task',title='中文\n标题',state='running')
        fields=sync_packet(4,[task],True,123,123,0,True).decode().strip().split('\t')
        self.assertEqual(fields[:8],['SC5','4','1','ok','123','123','0','1'])
        self.assertEqual(fields[10],'中文 标题')
        self.assertEqual(sync_packet(5,[],False,456,None,9999999,False).decode().strip().split('\t'),['SC5','5','0','unavailable','456','-','604800','0'])

    def test_ble_reconnect_and_source_error_remain_distinct(self):
        with tempfile.TemporaryDirectory() as root:
            source=SimpleNamespace(snapshot=lambda:[dict(id='task',title='私密标题',state='done',done_key='old')])
            links=[]
            def factory(*args):link=FakeBle();links.append(link);return link
            bridge=Bridge(source,root,transport='ble',ble_device='0123456789ab',ble_factory=factory)
            bridge.step();self.assertEqual(bridge.link_transport,'ble');self.assertFalse(bridge.baseline_pending)
            first_good=bridge.last_good_at
            source.snapshot=lambda:(_ for _ in ()).throw(OSError())
            bridge.step();state=json.loads((Path(root)/'status.json').read_text())
            self.assertEqual(state['connection'],'connected');self.assertEqual(state['data_source'],'unavailable');self.assertEqual(state['last_good_at'],first_good)
            self.assertIn(b'\tunavailable\t',links[0].packet)
            links[0].fail=True;bridge.last_sent_at-=6;bridge.step();self.assertTrue(links[0].closed)
            state=json.loads((Path(root)/'status.json').read_text());self.assertEqual(state['connection'],'waiting_ble');self.assertNotIn('私密',json.dumps(state))
            bridge.next_connect_at=0;bridge.step();self.assertEqual(len(links),2);self.assertEqual(links[-1].packet.split(b'\t')[7],b'1')

    def test_bound_helper_paths_are_regenerated_for_new_mac(self):
        loc=service.Locations('/tmp/新电脑 with spaces')
        args=service.make_plist(loc,dict(serial_number='x',codex_home='/tmp/.codex',transport='ble',ble_device='0123456789ab'))['ProgramArguments']
        self.assertIn(str(loc.root/'ble.key'),args)
        self.assertIn(str(loc.root/'微光蓝牙.app/Contents/MacOS/WeiguangBluetooth'),args)
        self.assertNotIn('--key',args)

    def test_missing_binding_never_launches_or_connects(self):
        with patch('ble_link.subprocess.Popen') as popen:
            with self.assertRaises(BleError):BleLink('/missing/helper','0123456789ab','/missing/key').open()
            popen.assert_not_called()

if __name__=='__main__':unittest.main()
