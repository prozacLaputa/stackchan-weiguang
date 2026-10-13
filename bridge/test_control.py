import json
from pathlib import Path
import queue
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from control import Command, ControlServer, parse_device, request, validate_request
from runtime import Bridge
from test_runtime import FakeSerial, port, task


def report(seq):
    return f'DEVICE\t{seq}\t0.24\t83\t1\thome\t0\t70\t1\t1\t1\t0\t42\t0\n'.encode()


class Link(FakeSerial):
    mode='normal'
    def write(self,data):
        super().write(data)
        self.request=data
    def readline(self):
        fields=self.request.strip().split(b'\t')
        if fields[0]==b'SC5':return super().readline()
        if self.mode=='legacy':return b'ERROR\tcommand\n'
        if self.mode=='save_failed':return b'DEVICE_ERROR\t'+fields[1]+b'\tsave_failed\n'
        return report(fields[1].decode())


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.hub=ControlServer(self.root);self.link=Link()
        self.bridge=Bridge(SimpleNamespace(snapshot=lambda:[task()]),self.root,control=self.hub,
                           serial_factory=lambda:self.link,port_provider=lambda:[port()])

    def test_protocol_rejects_malformed_out_of_range_and_arbitrary_commands(self):
        for value in ({'action':'PET_DEMO'}, {'action':'inspect','extra':1}, {'action':'configure','changes':{}},
                      {'action':'configure','changes':{'light':True}}, {'action':'configure','changes':{'rest':5}},
                      {'action':'configure','changes':{'motor':1}}):
            with self.assertRaises(ValueError):validate_request(value)
        self.assertEqual(parse_device(report(7),7)['battery'],83)
        for raw in (report(8),report(7).replace(b'\t83\t',b'\t101\t'),report(7).replace(b'home',b'other'),b'DEVICE\t7'):
            with self.assertRaises(ValueError):parse_device(raw,7)

    def test_shared_connection_returns_state_without_replaying_notifications(self):
        self.bridge.step()
        self.assertTrue(self.bridge.device_supported)
        self.assertEqual(self.bridge.device['firmware'],'0.24')
        seqs=[p for p in self.link.packets if p.startswith(b'SC5')]
        command=Command({'action':'configure','changes':{'light':2}});self.hub.queue.put(command)
        self.bridge.step()
        self.assertTrue(command.result['ok'])
        self.assertTrue(self.link.packets[-1].endswith(b'\t2\t-\t-\n'))
        self.assertEqual(seqs,[p for p in self.link.packets if p.startswith(b'SC5')])
        state=json.loads((self.root/'status.json').read_text())
        self.assertEqual(state['device']['charging'],1)
        self.assertNotIn('私密',json.dumps(state,ensure_ascii=False))

    def test_expired_and_disconnected_changes_never_replay(self):
        command=Command({'action':'configure','changes':{'pet':0}});command.expires-=10
        self.hub.queue.put(command);self.bridge.step()
        self.assertFalse(command.result['ok'])
        self.assertFalse(any(p.startswith(b'DEVICE_SET') for p in self.link.packets))
        self.bridge.disconnect()
        command=Command({'action':'configure','changes':{'rest':3}});self.hub.queue.put(command)
        self.bridge.maintain_device()
        self.assertEqual(command.result['error'],'device_unavailable')
        self.bridge.next_connect_at=0;self.bridge.step()
        self.assertFalse(any(p.startswith(b'DEVICE_SET') for p in self.link.packets))

    def test_legacy_firmware_and_save_failure_not_success(self):
        self.link.mode='legacy';self.bridge.step();self.assertFalse(self.bridge.device_supported)
        size=len(self.link.packets);self.bridge.step();self.assertEqual(len(self.link.packets),size)
        cmd=Command({'action':'configure','changes':{'pet':0}});self.hub.queue.put(cmd);self.bridge.step()
        self.assertEqual(cmd.result['error'],'firmware_update_required')
        self.bridge.disconnect();self.bridge.next_connect_at=0;self.link.mode='normal';self.bridge.step()
        self.link.mode='save_failed';cmd=Command({'action':'configure','changes':{'pet':0}});self.hub.queue.put(cmd);self.bridge.step()
        self.assertEqual(cmd.result,{'ok':False,'error':'save_failed'})
        self.assertEqual(self.bridge.device_error,'save_failed')

    def test_v25_notification_settings_and_old_firmware_compatibility(self):
        new=report(7).replace(b'0.24',b'0.25').rstrip()+b'\t1\t0\n'
        self.assertEqual(parse_device(new,7)['wait_motion'],1)
        self.assertEqual(parse_device(new,7)['done_motion'],0)
        current=new.replace(b'0.25',b'0.26')
        self.assertEqual(parse_device(current,7)['firmware'],'0.26')
        self.assertEqual(parse_device(new.replace(b'0.25',b'0.28'),7)['firmware'],'0.28')
        self.assertEqual(parse_device(new.replace(b'0.25',b'0.29'),7)['firmware'],'0.29')
        self.assertEqual(parse_device(current,7)['wait_motion'],1)
        for bad in (new.rstrip()+b'\t0',new.replace(b'\t1\t0\n',b'\t2\t0\n'),new.replace(b'0.25',b'0.24')):
            with self.assertRaises(ValueError):parse_device(bad,7)
        self.bridge.step() # Existing v0.24 keeps its old settings, new switches unsupported.
        cmd=Command({'action':'configure','changes':{'wait_motion':1}});self.hub.queue.put(cmd);self.bridge.step()
        self.assertEqual(cmd.result['error'],'firmware_update_required')
        self.assertFalse(any(p.startswith(b'DEVICE_SET') for p in self.link.packets))
        self.bridge.device=parse_device(current,7)
        cmd=Command({'action':'configure','changes':{'wait_motion':1,'done_motion':0}});self.hub.queue.put(cmd);self.bridge.step()
        self.assertTrue(self.link.packets[-1].endswith(b'\t-\t-\t-\t1\t0\n'))
        for changes in ({'wait_motion':2},{'done_motion':True},{'done_motion':-1}):
            with self.assertRaises(ValueError):validate_request({'action':'configure','changes':changes})

    def test_robot_changes_are_polled_without_a_mac_write(self):
        self.bridge.step()
        old=self.bridge.last_device_query
        remote=report('unused').replace(b'\t70\t1\t1\t1\t',b'\t40\t0\t2\t0\t')
        def receive_robot_state():
            seq=self.link.request.strip().split(b'\t')[1]
            return remote.replace(b'unused',seq)
        with patch('runtime.time.monotonic',return_value=old+2.1), patch.object(self.link,'readline',side_effect=receive_robot_state):
            self.bridge.maintain_device()
        self.assertEqual(self.bridge.device['light'],0)
        self.assertEqual(self.bridge.device['rest'],2)
        self.assertEqual(self.bridge.device['pet'],0)
        self.assertFalse(any(p.startswith(b'DEVICE_SET') for p in self.link.packets))
        state=json.loads((self.root/'status.json').read_text())
        self.assertEqual(state['device']['light'],0)

    def test_private_socket_end_to_end_and_shutdown(self):
        self.hub.start();self.addCleanup(self.hub.close)
        self.assertEqual(self.hub.path.stat().st_mode&0o777,0o600)
        reply=[];worker=threading.Thread(target=lambda:reply.append(request(self.root,{'action':'inspect'})))
        worker.start()
        deadline=time.monotonic()+2
        while self.hub.queue.empty() and time.monotonic()<deadline:time.sleep(.01)
        self.bridge.step();worker.join(2)
        self.assertFalse(worker.is_alive());self.assertTrue(reply[0]['ok'])


if __name__=='__main__':unittest.main()
