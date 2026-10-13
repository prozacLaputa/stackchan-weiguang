import unittest
from unittest.mock import patch
from control import Command, parse_device, validate_request
from test_companion_settings import v35
import test_control


def v37(seq=7, skin=1):
    return v35(seq).replace(b'0.35', b'0.37').rstrip() + f'\t{skin}\n'.encode()


class SkinTests(unittest.TestCase):
    def test_version_field_and_validation(self):
        self.assertEqual(parse_device(v37(), 7)['skin'], 1)
        self.assertEqual(parse_device(v37().replace(b'0.37', b'0.38'), 7)['skin'], 1)
        self.assertEqual(parse_device(v37().replace(b'0.37', b'0.39'), 7)['skin'], 1)
        self.assertEqual(parse_device(v37().replace(b'0.37', b'0.40').replace(b'home', b'focus'), 7)['page'], 'focus')
        self.assertNotIn('skin', parse_device(v35(), 7))
        for value in (-1, 2, 'x'):
            with self.assertRaises(ValueError):
                parse_device(v37(skin=value), 7)
        for raw in (v37().replace(b'0.37', b'0.36'), v37().rstrip().rsplit(b'\t', 1)[0], v37().rstrip()+b'\t0'):
            with self.assertRaises(ValueError):
                parse_device(raw, 7)
        for value in (-1, 2, True, '1'):
            with self.assertRaises(ValueError):
                validate_request({'action': 'configure', 'changes': {'skin': value}})

    def test_old_firmware_rejects_and_partial_update_uses_ten_fields(self):
        fixture = test_control.ControlTests();fixture.setUp()
        try:
            fixture.bridge.step();fixture.bridge.device = parse_device(v35(), 7)
            old_count = len(fixture.link.packets)
            command = Command({'action': 'configure', 'changes': {'skin': 1}})
            fixture.hub.queue.put(command);fixture.bridge.maintain_device()
            self.assertEqual(command.result['error'], 'firmware_update_required')
            self.assertEqual(len(fixture.link.packets), old_count)
            fixture.bridge.device = parse_device(v37(), 7)
            def reply():
                return v37(int(fixture.link.request.strip().split(b'\t')[1]))
            with patch.object(fixture.link, 'readline', side_effect=reply):
                for changes, expected in (({'skin': 1}, ['-']*9+['1']), ({'light': 2}, ['2']+['-']*9)):
                    command = Command({'action': 'configure', 'changes': changes})
                    fixture.hub.queue.put(command);fixture.bridge.maintain_device()
                    self.assertTrue(command.result['ok'])
                    self.assertEqual(fixture.link.packets[-1].decode().strip().split('\t')[2:], expected)
        finally:
            fixture.doCleanups()
