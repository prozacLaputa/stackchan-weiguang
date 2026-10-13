import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from control import Command,ControlServer,parse_companion,validate_request
from runtime import Bridge
from test_runtime import FakeSerial

class Link(FakeSerial):
    phase='off';left=0;total=0;state='awake';mode='ok'
    def write(self,data):
        super().write(data);self.fields=data.decode().strip().split('\t')
        if self.fields[0]=='COMPANION_SET':self.state=self.fields[2]
        if self.fields[0]=='FOCUS_SET' and self.mode=='ok':
            if self.fields[2]=='start':self.phase='running';self.total=self.left=int(self.fields[3])*60
            else:self.phase='off';self.total=self.left=0
    def readline(self):
        if self.mode=='bad':return f'COMPANION\t{self.fields[1]}\tbad\toff\t0\t0\t0'.encode()
        if self.mode=='busy':return f'COMPANION_ERROR\t{self.fields[1]}\tbusy'.encode()
        return f'COMPANION\t{self.fields[1]}\t{self.state}\t{self.phase}\t{self.left}\t{self.total}\t0'.encode()

class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.hub=ControlServer(self.root);self.link=Link();self.link.port='test-ble'
        self.bridge=Bridge(SimpleNamespace(),self.root,control=self.hub,presence=SimpleNamespace(snapshot=lambda:('awake',123)))
        self.bridge.link=self.link;self.bridge.link_transport='ble';self.bridge.baseline_pending=False
        self.bridge.device={'firmware':'0.34'}

    def test_requests_and_wire_validation(self):
        for v in ({'action':'focus','operation':'start','minutes':1},{'action':'focus','operation':'start','minutes':True},
                  {'action':'focus','operation':'stop','minutes':0},{'action':'focus','operation':'restart'}):
            with self.assertRaises(ValueError):validate_request(v)
        for minutes in (15,25,45):validate_request({'action':'focus','operation':'start','minutes':minutes})
        good=b'COMPANION\t1\tawake\trunning\t100\t1500\t0'
        self.assertEqual(parse_companion(good,1)['remaining'],100)
        for bad in (good.replace(b'100',b'0'),good.replace(b'1500',b'10'),good.replace(b'running',b'off'),good+b'\t1',good.replace(b'awake',b'bad')):
            with self.assertRaises(ValueError):parse_companion(bad,1)

    def test_timer_commands_and_presence_share_link_without_restarting_timer(self):
        command=Command({'action':'focus','operation':'start','minutes':25});self.hub.queue.put(command)
        self.bridge.maintain_device();self.assertTrue(command.result['ok']);self.assertEqual(self.bridge.companion['remaining'],1500)
        self.link.left=1200;self.bridge.last_companion_query=0;self.bridge.maintain_companion()
        self.assertEqual(self.bridge.companion['remaining'],1200)
        self.assertEqual(sum(p.startswith(b'FOCUS_SET') for p in self.link.packets),1)
        self.assertIn(b'awake\t123',self.link.packets[-1])
        saved=json.loads((self.root/'status.json').read_text());self.assertEqual(saved['companion']['total'],1500)
        command=Command({'action':'focus','operation':'stop'});self.hub.queue.put(command);self.bridge.maintain_device()
        self.assertTrue(command.result['ok']);self.assertEqual(self.bridge.companion['focus_state'],'off')

    def test_expired_disconnected_old_and_invalid_never_queue_future_start(self):
        command=Command({'action':'focus','operation':'start','minutes':15});command.expires-=10
        self.hub.queue.put(command);self.bridge.maintain_device();self.assertFalse(self.link.packets)
        self.bridge.disconnect();command=Command({'action':'focus','operation':'start','minutes':15});self.hub.queue.put(command)
        self.bridge.maintain_device();self.assertEqual(command.result['error'],'device_unavailable')
        self.bridge.link=self.link;self.bridge.baseline_pending=False;self.bridge.device={'firmware':'0.33'}
        self.bridge.maintain_companion(command=Command({'action':'focus','operation':'start','minutes':15}));self.assertFalse(self.link.packets)
        self.bridge.device={'firmware':'0.34'};self.link.mode='bad';self.bridge.maintain_companion()
        self.assertIsNone(self.bridge.link);self.assertEqual(self.bridge.companion_error,'device_unavailable')

    def test_busy_is_not_success_or_a_disconnect(self):
        self.link.mode='busy';command=Command({'action':'focus','operation':'start','minutes':15})
        self.bridge.maintain_companion(command=command)
        self.assertEqual(command.result,{'ok':False,'error':'busy'});self.assertIs(self.bridge.link,self.link)
