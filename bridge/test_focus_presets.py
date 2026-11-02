import unittest
from control import validate_request,parse_companion,Command
import test_companion

class FocusPresetProtocolTests(unittest.TestCase):
    def test_preset_wire_ack_and_errors_preserve_active_timer(self):
        fixture=test_companion.CompanionTests();fixture.setUp()
        class Link(test_companion.Link):
            error='';port='test-ble'
            def readline(self):
                if self.error:return f'COMPANION_ERROR\t{self.fields[1]}\t{self.error}'.encode()
                return f'COMPANION\t{self.fields[1]}\tawake\trunning\t7100\t7200\t0\tfocus\t7200\t1\t0\t0\t0\t0\t1\t37\t0'.encode()
        try:
            link=Link();fixture.bridge.link=link;fixture.bridge.device={'firmware':'0.50'}
            command=Command({'action':'focus','operation':'add_preset','minutes':37,'expected_revision':0})
            fixture.bridge.maintain_companion(command=command)
            self.assertTrue(command.result['ok'])
            self.assertEqual(link.fields[0],'FOCUS_PRESET');self.assertEqual(link.fields[2:],['0','add','37'])
            self.assertEqual(command.result['companion']['custom_minutes'],[37])
            self.assertEqual(command.result['companion']['remaining'],7100)
            for error in ('conflict','full','save_failed'):
                link.error=error
                command=Command({'action':'focus','operation':'remove_preset','minutes':37,'expected_revision':1})
                fixture.bridge.maintain_companion(command=command)
                self.assertEqual(command.result,{'ok':False,'error':error})
                self.assertIs(fixture.bridge.link,link)
                self.assertEqual(fixture.bridge.companion['remaining'],7100)
            self.assertFalse(any(p.startswith(b'FOCUS_SET') for p in link.packets))
        finally:fixture.doCleanups()
    def test_duration_and_mutation_validation(self):
        for m in (1,30,60,120,240):validate_request({'action':'focus','operation':'start','minutes':m})
        for m in (True,0,241,1.5,'30'):
            with self.assertRaises(ValueError):validate_request({'action':'focus','operation':'start','minutes':m})
        base={'action':'focus','operation':'add_preset','minutes':37,'expected_revision':0}
        self.assertEqual(validate_request(base),base)
        for patch in ({'expected_revision':True},{'minutes':241},{'operation':'reset_presets'},{'extra':1}):
            with self.assertRaises(ValueError):validate_request(base|patch)
    def test_extended_report_and_old_bounds(self):
        base='COMPANION\t8\tawake\trunning\t7200\t7200\t0\tfocus\t7200\t1\t0\t0\t0\t0'
        raw=(base+'\t2\t37,240\t0').encode()
        self.assertEqual(parse_companion(raw,8)['custom_minutes'],[37,240])
        self.assertEqual(parse_companion(raw,8)['total'],7200)
        with self.assertRaises(ValueError):parse_companion(base.encode(),8)
        for suffix in ('\t2\t60\t0','\t0\t37\t0','\t2\t37,37\t0','\t2\t240,37\t0','\t2\t0\t0','\t2\t241\t0','\t2\t1,2,3,4,5,6,7\t0','\t-1\t-\t0','\t2\t-\t2'):
            with self.assertRaises(ValueError):parse_companion((base+suffix).encode(),8)
    def test_old_firmware_does_not_receive_unsupported_request(self):
        fixture=test_companion.CompanionTests();fixture.setUp()
        try:
            for req in ({'action':'focus','operation':'start','minutes':120},{'action':'focus','operation':'add_preset','minutes':37,'expected_revision':0}):
                command=Command(req);fixture.bridge.maintain_companion(command=command)
                self.assertEqual(command.result['error'],'firmware_update_required')
            self.assertFalse(fixture.link.packets)
        finally:fixture.doCleanups()
