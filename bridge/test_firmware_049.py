"""UI-only firmware revisions must retain all desktop capabilities."""
import unittest
from control import parse_device
import test_motion_recovery as recovery
import test_companion as companion
import test_sticky_note as note

class Firmware049Tests(unittest.TestCase):
    def test_full_report_keeps_settings_and_motion_fields(self):
        old=parse_device(recovery.report(),7)
        new=parse_device(recovery.report().replace(b'0.48',b'0.49'),7)
        self.assertEqual(new.pop('firmware'),'0.49');old.pop('firmware')
        self.assertEqual(new,old)

class Firmware049RecoveryTests(recovery.MotionRecoveryTests):
    def setUp(self):
        super().setUp();self.bridge.device['firmware']='0.49'

class Firmware049CompanionTests(companion.CompanionTests):
    def setUp(self):
        super().setUp();self.bridge.device={'firmware':'0.49'}

class Firmware049NoteTests(note.NoteTests):
    def setUp(self):
        super().setUp();self.bridge.device={'firmware':'0.49'}
