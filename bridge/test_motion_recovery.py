import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from control import Command,ControlServer,parse_device,validate_request
from diagnostics import Journal,clean_device,read_events,export_bundle
from runtime import Bridge
import service


def report(seq=7):
    fields=['DEVICE',str(seq),'0.48',100,0,'home',0,70,1,1,1,0,42,0,0,0,
            'unavailable','pet-follow-error',0,1,1,1,'failed','pet-follow-error',0,1,1,1,1,1,1,
            123,'pet-follow-error',1400,659,680,70,1,100,100,1]
    return ('\t'.join(map(str,fields))+'\n').encode()

class Link:
    port='fake-ble'
    def __init__(self,outcome='recovered'):self.packets=[];self.outcome=outcome;self.closed=False
    def write(self,raw):self.packets.append(raw)
    def readline(self):
        if self.outcome=='disconnect':raise OSError('lost')
        seq=self.packets[-1].split(b'\t')[1]
        return b'MOTION_RESULT\t'+seq+b'\t'+self.outcome.encode()+b'\n'
    def close(self):self.closed=True

class MotionRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.loc=service.Locations(self.tmp.name);self.loc.runtime.mkdir(parents=True)
        self.hub=ControlServer(self.loc.runtime);self.link=Link()
        self.bridge=Bridge(SimpleNamespace(snapshot=lambda:[]),self.loc.runtime,control=self.hub)
        self.bridge.link=self.link;self.bridge.link_transport='ble';self.bridge.baseline_pending=False
        self.bridge.device=parse_device(report(),7);self.bridge.device_at=time.time()
        self.bridge.device_error=None;self.bridge.last_data_ok=True
    def send(self,**request):
        cmd=Command(dict(action='motion_recover',fault_id=123,**request));self.hub.queue.put(cmd);self.bridge.maintain_device();return cmd.result
    def test_strict_request_and_wire_schema(self):
        self.assertEqual(parse_device(report(),7)['motion_fault_command'],680)
        for req in ({'action':'motion_recover'},{'action':'motion_recover','fault_id':True},
                    {'action':'motion_recover','fault_id':0},{'action':'motion_recover','fault_id':123,'force':True}):
            with self.assertRaises(ValueError):validate_request(req)
        for raw in (report()+b'\tx',report().replace(b'\t659\t',b'\t65536\t'),report().replace(b'pet-follow-error',b'private')):
            with self.assertRaises(ValueError):parse_device(raw,7)
    def test_one_command_and_preserved_fault_before_send(self):
        original=self.link.write
        def send_after_save(raw):
            saved=json.loads((self.loc.runtime/'motion-last-fault.json').read_text())
            self.assertEqual(saved['device']['motion_fault_position'],659)
            original(raw)
        self.link.write=send_after_save
        result=self.send();self.assertTrue(result['ok']);self.assertEqual(len(self.link.packets),1)
        self.assertTrue(self.link.packets[0].startswith(b'MOTION_RECOVER\t'))
        self.assertEqual((self.loc.runtime/'motion-last-fault.json').stat().st_mode&0o777,0o600)
    def test_error_or_lost_reply_is_not_replayed(self):
        for outcome in ('load-high','not-still','release-required','connection-lost','stale-fault','disconnect','arbitrary'):
            self.link=Link(outcome);self.bridge.link=self.link;self.bridge.baseline_pending=False;self.bridge.device_at=time.time()
            result=self.send();self.assertFalse(result['ok']);self.assertEqual(len(self.link.packets),1)
            self.bridge.link=Link();self.bridge.last_device_query=time.monotonic();self.bridge.maintain_device();self.assertFalse(any(x.startswith(b'MOTION_RECOVER') for x in self.bridge.link.packets))
    def test_expired_disconnected_old_and_unrecorded_requests_do_not_send(self):
        cmd=Command({'action':'motion_recover','fault_id':123});cmd.expires-=10;self.hub.queue.put(cmd)
        self.bridge.maintain_device();self.assertFalse(self.link.packets)
        self.bridge.device_at=time.time()-11;self.assertEqual(self.send()['motion_result'],'stale-fault');self.assertFalse(self.link.packets)
        self.bridge.device_at=time.time();self.bridge.device['firmware']='0.47';self.assertEqual(self.send()['error'],'firmware_update_required')
        self.bridge.device['firmware']='0.48'
        with patch.object(self.bridge.diagnostics,'capture_motion_fault',side_effect=OSError('full')):
            self.assertEqual(self.send()['motion_result'],'diagnostic-save-failed')
        self.assertFalse(self.link.packets)
        self.bridge.link=None;self.assertEqual(self.send()['error'],'device_unavailable')
    def test_snapshot_survives_recovery_and_is_exported_sanitized(self):
        d=self.bridge.device;d['secret']='DO_NOT_EXPORT'
        self.bridge.status('connected',True)
        original=(self.loc.runtime/'motion-last-fault.json').read_bytes()
        d['motion_state']='checking';self.bridge.status('connected',True)
        self.assertNotIn('motion_recovered',[r['kind'] for r in read_events(self.loc.runtime)[0]])
        d.update(motion_state='ready',motion_reason='none',motion_recoverable=0)
        self.bridge.status('connected',True)
        self.assertEqual(original,(self.loc.runtime/'motion-last-fault.json').read_bytes())
        self.assertIn('motion_recovered',[r['kind'] for r in read_events(self.loc.runtime)[0]])
        self.assertNotIn('DO_NOT_EXPORT',original.decode())
        import zipfile
        result=export_bundle(self.loc,{'fresh':True})
        with zipfile.ZipFile(result['path']) as z:
            self.assertIn('last-motion-fault.json',z.namelist())
            self.assertNotIn('DO_NOT_EXPORT',z.read('last-motion-fault.json').decode())

if __name__=='__main__':unittest.main()
