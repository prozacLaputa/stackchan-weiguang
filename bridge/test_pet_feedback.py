import json
import unittest
from unittest.mock import patch
import test_control
from test_control import report
from test_runtime import FakeSerial
from control import parse_device, Command


def current(seq=7):
    return report(seq).replace(b'0.24',b'0.30').rstrip()+b'\t0\t0\tready\tnone\t0\t1\t0\t0\tnone\tnone\t0\n'


class PetProtocolTests(unittest.TestCase):
    def test_v32_game_keeps_settings_and_sc7_without_new_control_commands(self):
        fixture=test_control.ControlTests();fixture.setUp()
        try:
            fixture.bridge.step()
            def receive():
                seq=int(fixture.link.request.strip().split(b'\t')[1])
                return current(seq).replace(b'0.30',b'0.32').replace(b'home',b'game')
            with patch.object(fixture.link,'readline',side_effect=receive):
                cmd=Command({'action':'inspect'});fixture.hub.queue.put(cmd);fixture.bridge.maintain_device()
                self.assertTrue(cmd.result['ok'])
                self.assertEqual(fixture.bridge.device['page'],'game')
                cmd=Command({'action':'configure','changes':{'wait_motion':0}})
                fixture.hub.queue.put(cmd);fixture.bridge.maintain_device()
                self.assertTrue(cmd.result['ok'])
            with patch.object(fixture.link,'readline',side_effect=lambda:FakeSerial.readline(fixture.link)):
                fixture.bridge.step()
            self.assertTrue(any(p.startswith(b'SC7') for p in fixture.link.packets))
            self.assertFalse(any(p.startswith((b'GAME_',b'IDLE_',b'MOTION_',b'PET_')) for p in fixture.link.packets))
            from diagnostics import clean_device
            self.assertEqual(clean_device(fixture.bridge.device)['page'],'game')
        finally:fixture.doCleanups()

    def test_v33_has_no_game_page_and_keeps_pet_feedback(self):
        raw=current().replace(b'0.30',b'0.33')
        self.assertEqual(parse_device(raw,7)['motion_state'],'ready')
        self.assertEqual(parse_device(raw.replace(b'home',b'list'),7)['page'],'list')
        with self.assertRaises(ValueError):parse_device(raw.replace(b'home',b'game'),7)

    def test_new_report_and_legacy(self):
        self.assertNotIn('motion_state',parse_device(report(7),7))
        device=parse_device(current(),7)
        self.assertEqual(device['motion_state'],'ready')
        self.assertEqual(device['pet_event'],0)
        self.assertEqual(device['head_sensor'],1)
        fault=current().replace(b'ready\tnone',b'unavailable\tload-high')
        self.assertEqual(parse_device(fault,7)['motion_reason'],'load-high')

    def test_bad_fields_are_rejected(self):
        for raw in (current().replace(b'ready',b'arbitrary'),current().replace(b'none',b'unsafe'),
                    current().rstrip()+b'\t0',current().replace(b'0.30',b'0.29'),
                    current().replace(b'none\t0\t1\t',b'none\t5001\t1\t'),
                    current().replace(b'none\t0\t1\t',b'none\t0\t2\t')):
            with self.assertRaises(ValueError):parse_device(raw,7)

    def test_max_reply_fits_encrypted_ble_notification(self):
        values=['DEVICE','4294967295','0.30','100','1','settings','1','255','3','4','1','1','4294967','4294967','1','1',
                'unavailable','pet-command-ack','5000','1','4294967295','4294967','completed','release-required','1']
        raw=('\t'.join(values)+'\n').encode()
        self.assertLessEqual(len(raw),256)
        parse_device(raw,4294967295)

    def test_real_bridge_status_and_sc7_keep_working(self):
        # 复用实际桥接 fixture，不复制实现；从设备回执走到 status.json。
        fixture=test_control.ControlTests();fixture.setUp()
        try:
            fixture.bridge.step()
            def receive():
                seq=int(fixture.link.request.strip().split(b'\t')[1])
                return current(seq)
            with patch.object(fixture.link,'readline',side_effect=receive):
                cmd=Command({'action':'inspect'});fixture.hub.queue.put(cmd);fixture.bridge.maintain_device()
            state=json.loads((fixture.root/'status.json').read_text())
            self.assertTrue(cmd.result['ok'])
            self.assertEqual(state['device']['motion_state'],'ready')
            self.assertEqual(state['device']['firmware'],'0.30')
            self.assertFalse(any(b'PET_DEMO' in packet for packet in fixture.link.packets))
            with patch.object(fixture.link,'readline',side_effect=lambda:FakeSerial.readline(fixture.link)):
                fixture.bridge.step()
            self.assertTrue(fixture.bridge.link)
            self.assertTrue(any(packet.startswith(b'SC7') for packet in fixture.link.packets))
        finally:fixture.doCleanups()
