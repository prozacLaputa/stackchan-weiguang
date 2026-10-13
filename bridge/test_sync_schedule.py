"""覆盖变更推送、心跳与故障重连；时间由测试控制，无真实等待。"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest
from runtime import Bridge
from test_runtime import FakeSerial, port, task

class ScheduleTests(unittest.TestCase):
 def test_changed_state_immediate_unchanged_heartbeat_and_retry(self):
  with tempfile.TemporaryDirectory() as root:
   clock=[100.0];rows=[task()];links=[]
   def factory():
    link=FakeSerial();links.append(link);return link
   bridge=Bridge(SimpleNamespace(snapshot=lambda:rows),root,serial_factory=factory,port_provider=lambda:[port()])
   with patch('runtime.time.monotonic',side_effect=lambda:clock[0]):
    bridge.step();self.assertEqual(len(links[0].packets),1)
    for i in range(1,25):clock[0]=100+i*.2;bridge.step()
    self.assertEqual(len(links[0].packets),1)
    clock[0]=105;bridge.step();self.assertEqual(len(links[0].packets),2)
    rows[0]=dict(rows[0],state='needs_input',wait_key='q2');clock[0]=105.2;bridge.step()
    self.assertEqual(len(links[0].packets),3);self.assertIn(b'needs_input',links[0].packets[-1])
    clock[0]=105.4;bridge.step();self.assertEqual(len(links[0].packets),3)
    links[0].fail=True;clock[0]=111;bridge.step();self.assertIsNone(bridge.link)
    clock[0]=113;bridge.step();self.assertEqual(len(links),2)
    self.assertEqual(links[-1].packets[-1].split(b'\t')[7],b'1')
    self.assertEqual(links[-1].packets[-1].split(b'\t')[12],b'-')

 def test_unplugged_polling_is_bounded(self):
  with tempfile.TemporaryDirectory() as root:
   clock=[100.0];discoveries=[]
   def ports():discoveries.append(clock[0]);return []
   bridge=Bridge(SimpleNamespace(snapshot=lambda:[]),root,port_provider=ports)
   with patch('runtime.time.monotonic',side_effect=lambda:clock[0]):
    for i in range(20):clock[0]=100+i*.2;bridge.step()
   self.assertEqual(len(discoveries),2)

if __name__=='__main__':unittest.main()
