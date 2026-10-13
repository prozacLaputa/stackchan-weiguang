import calendar
import time
import unittest
from unittest.mock import patch
from control import parse_companion, parse_device
import test_companion

class FocusSummaryTests(unittest.TestCase):
    def test_summary_reply_validation_and_legacy(self):
        base=b'COMPANION\t8\tawake\toff\t0\t0\t0\tfocus\t1500\t0'
        self.assertNotIn('today_day',parse_companion(base,8))
        self.assertEqual(parse_companion(base+b'\t20738\t3020\t2\t0',8)['today_seconds'],3020)
        self.assertEqual(parse_companion(base+b'\t0\t0\t0\t0',8)['today_day'],0)
        for tail in (b'\t0\t2\t0\t0',b'\t20738\t-1\t0\t0',b'\t20738\t86401\t0\t0',b'\t20738\t0\t1441\t0',b'\t20738\t0\t0\t2',b'\t99999\t0\t0\t0',b'\t20738\t0\t0'):
            with self.assertRaises(ValueError):parse_companion(base+tail,8)

    def test_local_date_only_sent_to_supported_firmware(self):
        fixture=test_companion.CompanionTests();fixture.setUp()
        try:
            for version in ('0.44','0.45'):
                fixture.bridge.device={'firmware':version};fixture.bridge.last_companion_query=0
                fixture.bridge.maintain_companion()
                fields=fixture.link.fields
                self.assertEqual(len(fields),5 if version=='0.45' else 4)
                if version=='0.45':self.assertAlmostEqual(int(fields[4]),calendar.timegm(time.localtime()),delta=2)
        finally:fixture.doCleanups()
