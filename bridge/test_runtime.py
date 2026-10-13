import json
from pathlib import Path
import sqlite3
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from runtime import (Bridge, NotificationGate, TaskSource, find_database, select_port,
                     single_instance, atomic_json)
import service


def port(name='/dev/cu.usbmodem1', number='robot'):
    return SimpleNamespace(device=name, vid=0x303a, pid=0x1001, serial_number=number)


def task(key='old'):
    return dict(id='one', state='done', title='私密任务标题', done_key=key, wait_key='', mood='idle', updated=0)


class FakeSerial:
    def __init__(self):
        self.is_open = False
        self.packets = []
        self.seq = None
        self.fail = False

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def write(self, data):
        if self.fail:
            raise OSError('拔线')
        self.packets.append(data)
        if data.startswith((b'SC5',b'SC6',b'SC7',b'SC8')):
            self.seq = data.split(b'\t')[1]

    def readline(self):
        return b'ACK\t' + self.seq + b'\n'


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.current = [task()]
        self.source = SimpleNamespace(snapshot=lambda: self.current)
        self.ports = [port()]
        self.serials = []
        def factory():
            serial = FakeSerial()
            self.serials.append(serial)
            return serial
        self.bridge = Bridge(self.source, self.root, serial_number='robot', serial_factory=factory,
                             port_provider=lambda: self.ports)

    def last_packet(self):
        fields=[p for p in self.serials[-1].packets if p.startswith(b'SC5')][-1].decode().strip().split('\t')
        return fields[:3]+fields[8:]

    def test_reconnect_new_port_and_no_replayed_completion(self):
        self.bridge.step()
        self.assertEqual(self.last_packet()[6], '-')
        self.current = [task('new')]
        self.bridge.step()
        self.assertEqual(self.last_packet()[6], 'new')
        self.serials[-1].fail = True
        self.bridge.last_sent_at -= 6
        self.bridge.step()
        self.assertIsNone(self.bridge.link)
        self.ports = []
        self.bridge.step()
        self.assertEqual(json.loads((self.root/'status.json').read_text())['connection'], 'waiting_usb')
        self.ports = [port('/dev/cu.usbmodem999')]
        self.bridge.next_connect_at=0
        self.bridge.step()
        self.assertEqual(self.serials[-1].port, '/dev/cu.usbmodem999')
        self.assertEqual(self.last_packet()[6], '-')
        self.bridge.step()
        self.assertEqual(self.last_packet()[6], '-')
        self.current = [task('after-reconnect')]
        self.bridge.step()
        self.assertEqual(self.last_packet()[6], 'after-reconnect')

    def test_sleep_gap_and_data_failure_rebaseline(self):
        self.bridge.step()
        self.current = [task('completed-during-sleep')]
        self.bridge.last_cycle -= 60
        self.bridge.step()
        self.assertEqual(len(self.serials), 2)
        self.assertEqual(self.last_packet()[6], '-')
        self.source.snapshot = lambda: (_ for _ in ()).throw(sqlite3.OperationalError('schema changed'))
        self.bridge.step()
        self.assertEqual(self.last_packet()[4], 'unknown')
        self.assertEqual(self.last_packet()[6], '-')
        self.source.snapshot = lambda: [task('during-data-failure')]
        self.bridge.step()
        self.assertEqual(self.last_packet()[6], '-')
        self.assertNotIn('私密', (self.root/'status.json').read_text())

    def test_no_device_does_not_open_or_spin(self):
        self.ports = []
        self.bridge.step()
        self.assertEqual(self.serials, [])
        self.assertFalse(json.loads((self.root/'status.json').read_text())['error'])

    def test_serial_controls_never_request_reset(self):
        self.bridge.step()
        serial = self.serials[0]
        self.assertFalse(serial.dtr)
        self.assertFalse(serial.rts)
        self.assertTrue(serial.exclusive)
        self.assertTrue(all(p.startswith(b'SC5\t') for p in serial.packets))

    def test_reason_capability_and_question_change_refresh_without_new_wait_event(self):
        self.current=[dict(task(),state='needs_input',wait_key='same-question',wait_reason='待答：第一项')]
        self.bridge.step()
        self.assertTrue(self.serials[-1].packets[-1].startswith(b'SC5'))
        self.bridge.device={'firmware':'0.28'};self.bridge.device_supported=True
        self.bridge.step()
        first=self.serials[-1].packets[-1]
        self.assertTrue(first.startswith(b'SC6'));self.assertIn('待答：第一项'.encode(),first)
        self.current[0]['wait_reason']='待答：剩余第二项'
        self.bridge.step()
        second=self.serials[-1].packets[-1]
        self.assertNotEqual(first,second);self.assertIn('待答：剩余第二项'.encode(),second)
        self.assertEqual(second.decode().strip().split('\t')[12],'-')
        self.source.snapshot=lambda: (_ for _ in ()).throw(sqlite3.OperationalError('unavailable'))
        self.bridge.step()
        self.assertNotIn('待答：'.encode(),self.serials[-1].packets[-1])


class DiscoveryTests(unittest.TestCase):
    def test_bound_identity_and_ambiguity(self):
        self.assertEqual(select_port([port(number='other'), port('/dev/cu.usb2')], 'robot'), '/dev/cu.usb2')
        self.assertIsNone(select_port([port(number='other')], 'robot'))
        with self.assertRaises(RuntimeError):
            select_port([port(), port('/dev/cu.usb2', 'other')])
        self.assertIsNone(select_port([port('/dev/tty.usbmodem1')]))

    def test_singleton_and_release(self):
        with tempfile.TemporaryDirectory() as root:
            with single_instance(root):
                with self.assertRaises(RuntimeError):
                    with single_instance(root):
                        pass
            with single_instance(root):
                pass

    def test_database_highest_version_no_stale_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            with self.assertRaises(FileNotFoundError):
                find_database(root)
            for name in ('state_5.sqlite', 'state_12.sqlite', 'state_99.sqlite.bak'):
                (root/name).touch()
            self.assertEqual(find_database(root).name, 'state_12.sqlite')
            with self.assertRaises(sqlite3.Error):
                TaskSource(root).snapshot()

    def test_gate_keeps_pending_state_but_suppresses_old_events(self):
        gate = NotificationGate()
        waiting = dict(task(), state='needs_input', wait_key='question')
        first = gate.filter([waiting])[0]
        self.assertEqual(first['state'], 'needs_input')
        self.assertEqual(first['wait_key'], '')
        self.assertEqual(gate.filter([dict(waiting, wait_key='question2')])[0]['wait_key'], 'question2')


class ServiceTests(unittest.TestCase):
    def test_plist_is_portable_and_does_not_pin_old_thread(self):
        loc = service.Locations('/tmp/新电脑 user with spaces')
        config = {'codex_home': '/tmp/新电脑 user/.codex', 'serial_number': 'AB:CD'}
        plist = service.make_plist(loc, config)
        args = plist['ProgramArguments']
        self.assertIn(str(loc.python), args)
        self.assertIn('AB:CD', args)
        self.assertNotIn('/dev/cu.usbmodem2101', args)
        self.assertEqual(args[-2:], ['--thread', ''])
        self.assertTrue(plist['RunAtLoad'])
        self.assertTrue(plist['KeepAlive'])
        self.assertNotIn('CODEX_THREAD_ID', plist['EnvironmentVariables'])

    def test_pause_disables_before_unloading_and_resume_enables(self):
        with tempfile.TemporaryDirectory() as root:
            loc = service.Locations(root)
            atomic_json(loc.config, dict(app_id=service.LABEL, codex_home=root, serial_number='test', paused=False))
            calls = []
            def launch(*args, **kwargs):
                calls.append(args)
                return SimpleNamespace(returncode=0 if args[0] != 'print' else 1, stdout='', stderr='')
            with patch.object(service, 'launch', launch):
                service.pause(loc)
                self.assertEqual(calls[0][0], 'disable')
                self.assertTrue(service.owned(loc)['paused'])
                with patch.object(service, 'check_usb_free'):
                    service.resume(loc)
                self.assertFalse(service.owned(loc)['paused'])
                self.assertIn(('enable', loc.target), calls)
                self.assertIn(('bootstrap', loc.domain, str(loc.plist)), calls)

    def test_stale_status_is_not_live_success(self):
        with tempfile.TemporaryDirectory() as root:
            loc = service.Locations(root)
            config = dict(app_id=service.LABEL, codex_home=root, serial_number='test', paused=False)
            atomic_json(loc.config, config)
            service.save_plist(loc, config)
            atomic_json(loc.runtime/'status.json', dict(pid=42, updated_at=time.time()-50, connection='connected'))
            with patch.object(service, 'installed', return_value=(True, 'pid = 42')):
                result = service.status(loc, True)
            self.assertFalse(result['fresh'])
            self.assertIsNone(result['bridge'])

if __name__ == '__main__':
    unittest.main()
