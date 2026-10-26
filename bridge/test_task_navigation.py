import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from task_actions import open_visible,parse_action_request
from runtime import Bridge
ID='00000000-0000-4000-8000-000000000001'
class TaskNavigationTests(unittest.TestCase):
 def test_visible_states_open_only_current_top8_unlocked(self):
  opener=Mock()
  for state in ('running','done','needs_input','unknown','interrupted'):
   source=SimpleNamespace(snapshot=lambda:[{'id':ID,'state':state}])
   self.assertEqual(open_visible(source,ID,'awake',opener),'opened')
  self.assertEqual(opener.call_count,5)
  opener.assert_called_with(f'codex://threads/{ID}?hostId=local');opener.reset_mock()
  source=SimpleNamespace(snapshot=lambda:[{'id':'other'}]*8+[{'id':ID}])
  self.assertEqual(open_visible(source,ID,'awake',opener),'stale')
  for presence in ('away','unknown'):self.assertEqual(open_visible(source,ID,presence,opener),'locked')
  self.assertEqual(open_visible(source,'file:///tmp/a','awake',opener),'stale');opener.assert_not_called()
  source.snapshot=Mock(side_effect=OSError());self.assertEqual(open_visible(source,ID,'awake',opener),'failed')
 def test_scope_is_explicit_and_strict(self):
  self.assertEqual(parse_action_request(f'ACTION\t2\t1\t{ID}'.encode(),2),(1,ID,'waiting'))
  self.assertEqual(parse_action_request(f'ACTION\t2\t1\t{ID}\ttask'.encode(),2),(1,ID,'task'))
  for raw in (f'ACTION\t2\t1\t{ID}\tother',f'ACTION\t2\t1\t{ID}\ttask\textra','ACTION\t2\t0\t-\ttask'):
   with self.assertRaises(ValueError):parse_action_request(raw.encode(),2)
 def test_generic_dispatch_once_and_legacy_path_kept(self):
  class Link:
   port='test'
   def write(self,raw):self.f=raw.decode().strip().split('\t')
   def readline(self):
    return f'ACTION_ACK\t{self.f[1]}'.encode() if self.f[0]=='ACTION_RESULT' else f'ACTION\t{self.f[1]}\t1\t{ID}\ttask'.encode()
   def close(self):pass
  with tempfile.TemporaryDirectory() as tmp:
   b=Bridge(SimpleNamespace(),Path(tmp),control=SimpleNamespace(),presence=SimpleNamespace(snapshot=lambda:('awake',0)))
   b.link=Link();b.link_transport='ble';b.baseline_pending=False;b.device={'firmware':'0.49'};b.last_data_ok=True;b.tasks=[{'id':ID,'state':'running'}]
   with patch('task_actions.open_visible',return_value='opened') as generic,patch('task_actions.open_pending') as waiting:
    b.maintain_actions();generic.assert_not_called()
    b.last_action_query=0;b.maintain_actions();generic.assert_called_once()
    b.last_action_query=0;b.maintain_actions();generic.assert_called_once();waiting.assert_not_called()
if __name__=='__main__':unittest.main()
