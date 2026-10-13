from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock
import tempfile
import unittest
from task_actions import open_pending, parse_action
from control import parse_companion, validate_request, Command
from runtime import Bridge

ID='00000000-0000-0000-0040-000000000001'
class ActionTests(unittest.TestCase):
    def test_opens_only_fresh_waiting_uuid_when_unlocked(self):
        source=SimpleNamespace(snapshot=lambda:[{'id':ID,'state':'needs_input','title':'example'}]);opener=Mock()
        self.assertEqual(open_pending(source,ID,'awake',opener),'opened')
        opener.assert_called_once_with(f'codex://threads/{ID}?hostId=local');opener.reset_mock()
        for presence in ('away','unknown'):
            self.assertEqual(open_pending(source,ID,presence,opener),'locked')
        self.assertEqual(open_pending(source,'../../file','awake',opener),'stale')
        source.snapshot=lambda:[{'id':ID,'state':'running'}]
        self.assertEqual(open_pending(source,ID,'awake',opener),'stale');opener.assert_not_called()
        source.snapshot=Mock(side_effect=OSError())
        self.assertEqual(open_pending(source,ID,'awake',opener),'failed')

    def test_wire_parser_strict_and_paused_clock(self):
        self.assertIsNone(parse_action(b'ACTION\t2\t0\t-',2))
        self.assertEqual(parse_action(f'ACTION\t2\t1\t{ID}'.encode(),2),(1,ID))
        for line in ('ACTION\t1\t1\t'+ID,'ACTION\t2\t0\t'+ID,'ACTION\t2\t4294967296\t'+ID,'ACTION\t2\t1\thttps://example.com','ACTION\t2\t1\t'+ID+'\textra'):
            with self.assertRaises(ValueError):parse_action(line.encode(),2)
        for op in ('pause','resume'):validate_request(dict(action='focus',operation=op))
        self.assertEqual(parse_companion(b'COMPANION\t2\tawake\tpaused\t900\t1500\t0',2)['remaining'],900)
        with self.assertRaises(ValueError):parse_companion(b'COMPANION\t2\tawake\tpaused\t0\t1500\t0',2)

    def test_dispatch_once_rearm_and_unavailable(self):
        class Link:
            port='test';event=1;mode='';closed=False
            def write(self,p):self.fields=p.decode().strip().split('\t')
            def readline(self):
                if self.fields[0]=='ACTION_RESULT':return f'ACTION_ACK\t{self.fields[1]}'.encode()
                return f'ACTION\t{self.fields[1]}\t{self.event}\t{ID}'.encode()
            def close(self):self.closed=True
        with tempfile.TemporaryDirectory() as temp:
            b=Bridge(SimpleNamespace(),Path(temp),control=SimpleNamespace(),presence=SimpleNamespace(snapshot=lambda:('awake',0)))
            link=Link();b.link=link;b.link_transport='ble';b.baseline_pending=False;b.device={'firmware':'0.40'};b.last_data_ok=True
            with patch('task_actions.open_pending',return_value='opened') as opener:
                b.maintain_actions();opener.assert_not_called() # Initial arm cannot dispatch.
                b.last_action_query=0;b.maintain_actions();self.assertEqual(opener.call_count,1)
                b.last_action_query=0;b.maintain_actions();self.assertEqual(opener.call_count,1) # duplicate reply
                link.event=2;b.last_data_ok=False;b.last_action_query=0;b.maintain_actions();self.assertEqual(opener.call_count,1)
                self.assertEqual(link.fields[-1],'failed')
                b.disconnect();self.assertFalse(b.actions_armed);self.assertEqual(b.last_action_id,0)

    def test_production_opener_uses_fixed_program_and_one_url(self):
        source=SimpleNamespace(snapshot=lambda:[{'id':ID,'state':'needs_input'}])
        with patch('subprocess.run') as run:
            self.assertEqual(open_pending(source,ID,'awake'),'opened')
            self.assertEqual(run.call_args.args[0],['/usr/bin/open',f'codex://threads/{ID}?hostId=local'])
            self.assertNotIn('shell',run.call_args.kwargs)

    def test_old_firmware_pause_not_sent(self):
        with tempfile.TemporaryDirectory() as temp:
            link=Mock();b=Bridge(SimpleNamespace(),Path(temp));b.link=link;b.device={'firmware':'0.39'};b.baseline_pending=False
            command=Command(dict(action='focus',operation='pause'));b.maintain_companion(command=command)
            self.assertEqual(command.result['error'],'firmware_update_required');link.write.assert_not_called()
