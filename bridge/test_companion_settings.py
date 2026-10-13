import unittest
from unittest.mock import patch
from control import Command,parse_device,validate_request
import test_control
from test_pet_feedback import current


def v35(seq=7):return current(seq).replace(b'0.30',b'0.35').rstrip()+b'\t1\t1\t1\t1\n'

class CompanionSettingsTests(unittest.TestCase):
    def test_wire_version_ranges_and_size(self):
        d=parse_device(v35(),7)
        self.assertEqual(parse_device(v35().replace(b'0.35',b'0.36'),7)['daily'],1)
        self.assertEqual([d[k] for k in ('daily','away_rest','greeting','affection')],[1,1,1,1])
        for raw in (v35().rstrip()+b'\t1',v35().replace(b'0.35',b'0.34'),v35().replace(b'home',b'game'),v35()[:-9]+b'\t3\t1\t1\t1\n'):
            with self.assertRaises(ValueError):parse_device(raw,7)
        values=['DEVICE','4294967295','0.35','100','1','settings','1','255','3','4','1','1','4294967','4294967','1','1','unavailable','not-initialized','5000','1','4294967295','4294967','completed','release-required','1','2','1','1','1']
        raw=('\t'.join(values)+'\n').encode();self.assertLessEqual(len(raw),256);parse_device(raw,4294967295)
        for changes in ({'daily':3},{'daily':True},{'greeting':2},{'affection':-1},{'away_rest':'1'}):
            with self.assertRaises(ValueError):validate_request({'action':'configure','changes':changes})

    def test_partial_changes_preserve_other_fields_and_old_firmware_rejects(self):
        fixture=test_control.ControlTests();fixture.setUp()
        try:
            fixture.bridge.step();old_count=len(fixture.link.packets)
            cmd=Command({'action':'configure','changes':{'daily':2}});fixture.hub.queue.put(cmd);fixture.bridge.maintain_device()
            self.assertEqual(cmd.result['error'],'firmware_update_required');self.assertEqual(len(fixture.link.packets),old_count)
            fixture.bridge.device=parse_device(v35(),7)
            def receive():return v35(int(fixture.link.request.strip().split(b'\t')[1]))
            with patch.object(fixture.link,'readline',side_effect=receive):
                cmd=Command({'action':'configure','changes':{'daily':0,'greeting':0}});fixture.hub.queue.put(cmd);fixture.bridge.maintain_device()
                self.assertTrue(cmd.result['ok']);self.assertTrue(fixture.link.packets[-1].endswith(b'\t-\t-\t-\t-\t-\t0\t-\t0\t-\n'))
                cmd=Command({'action':'configure','changes':{'light':2}});fixture.hub.queue.put(cmd);fixture.bridge.maintain_device()
                self.assertTrue(fixture.link.packets[-1].endswith(b'\t2\t-\t-\t-\t-\t-\t-\t-\t-\n'))
        finally:fixture.doCleanups()
