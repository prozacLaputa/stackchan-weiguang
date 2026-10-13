import unittest
from control import Command, parse_companion, validate_request
import test_companion

class FocusCycleTests(unittest.TestCase):
    def test_cycle_reply_and_legacy(self):
        old=b'COMPANION\t1\tawake\trunning\t42\t1500\t0'
        self.assertNotIn('stage',parse_companion(old,1))
        for raw in (old+b'\tfocus\t1500\t2',
                    b'COMPANION\t1\tawake\tpaused\t42\t300\t0\trest\t900\t2',
                    b'COMPANION\t1\tawake\tdone\t0\t300\t0\trest\t900\t2',
                    b'COMPANION\t1\tawake\toff\t0\t0\t0\tfocus\t1500\t0'):
            value=parse_companion(raw,1);self.assertIn('focus_total',value)
        good=b'COMPANION\t1\tawake\trunning\t42\t300\t0\trest\t900\t2'
        for bad in (good.replace(b'rest',b'unknown'),good.replace(b'\t300\t',b'\t299\t'),
                    good[:-1]+b'0',good.replace(b'\t900\t',b'\t901\t'),good+b'\t1',
                    good.replace(b'running\t42',b'off\t0')):
            with self.assertRaises(ValueError):parse_companion(bad,1)

    def test_next_command_requires_cycle_firmware(self):
        request={'action':'focus','operation':'next'};validate_request(request)
        with self.assertRaises(ValueError):validate_request(dict(request,minutes=25))
        fixture=test_companion.CompanionTests();fixture.setUp()
        try:
            fixture.bridge.device={'firmware':'0.43'}
            command=Command(request);fixture.bridge.maintain_companion(command=command)
            self.assertEqual(command.result['error'],'firmware_update_required');self.assertFalse(fixture.link.packets)
            fixture.bridge.device={'firmware':'0.44'}
            fixture.link.readline=lambda:f'COMPANION\t{fixture.link.fields[1]}\tawake\trunning\t900\t900\t0\tfocus\t900\t2'.encode()
            command=Command(request);fixture.bridge.maintain_companion(command=command)
            self.assertTrue(command.result['ok']);self.assertEqual(fixture.link.fields[2:],['next','0'])
            self.assertEqual(fixture.bridge.companion['round'],2)
        finally:fixture.doCleanups()
