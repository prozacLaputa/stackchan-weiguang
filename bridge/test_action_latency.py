import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from runtime import Bridge
ID='00000000-0000-4000-8000-000000000001'
class Clock:
 def __init__(self):self.now=100.;self.opened=None
 def time(self):return self.now
class Link:
 def __init__(self,c):self.clock=c;self.event_at=1e9;self.sent=False
 def write(self,raw):self.fields=raw.decode().strip().split('\t')
 def readline(self):
  f=self.fields;seq=f[1]
  if f[0].startswith('SC'):return f'ACK\t{seq}'.encode()
  if f[0]=='ACTION_RESULT':return f'ACTION_ACK\t{seq}'.encode()
  if f[0]=='ACTION_GET':
   event=not self.sent and self.clock.now>=self.event_at and f[2]=='poll'
   if event:self.sent=True
   return f'ACTION\t{seq}\t1\t{ID}'.encode() if event else f'ACTION\t{seq}\t0\t-'.encode()
  raise AssertionError(f)
 def close(self):pass

def sample(phase):
 c=Clock();tasks=[dict(id=ID,state='needs_input',title='test',wait_key='abcd',done_key='',mood='waiting')]
 with tempfile.TemporaryDirectory() as tmp:
  b=Bridge(SimpleNamespace(snapshot=lambda:tasks),Path(tmp),control=SimpleNamespace(),presence=SimpleNamespace(snapshot=lambda:('awake',0)))
  link=Link(c);b.link=link;b.link_transport='ble';b.device={'firmware':'0.49'};b.device_supported=True
  b.status=lambda *a,**kw:None;b.extras.observe=lambda *a:None
  # Use the real step and action exchange. Background device/voice I/O is excluded
  # here to isolate the avoidable scheduler delay, not estimate real radio latency.
  for name in ['maintain_voice','maintain_device','maintain_companion','maintain_note']:setattr(b,name,lambda *a:None)
  b.extras.maintain=lambda *a:None
  def opened(*a):c.opened=c.now;return 'opened'
  with patch('runtime.time.monotonic',c.time),patch('runtime.time.time',c.time),patch('task_actions.open_pending',side_effect=opened):
   b.step();link.event_at=100+phase+.3
   for tick in range(1,30):
    c.now=100+tick*.2;b.step()
    if c.opened is not None:return round(c.opened-(100+phase),4)
 raise AssertionError('not dispatched')
class ActionLatencyTests(unittest.TestCase):
 def test_waiting_hold_dispatch_does_not_wait_for_slow_poll_cadence(self):
  # Different touch phases must all be served by the next 200 ms bridge turn.
  # This traverses the production step and request/reply parser, never opens Codex.
  values=[sample(i/100) for i in range(0,80,2)]
  self.assertLessEqual(max(values),.5,values)

if __name__=='__main__':unittest.main()
