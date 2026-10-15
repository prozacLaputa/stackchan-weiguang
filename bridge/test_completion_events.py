import datetime as dt
import json
from pathlib import Path
import sqlite3
import tempfile
import time
from types import SimpleNamespace
import unittest

from monitor import Tracker
from runtime import Bridge
from task_actions import completion_events
from test_runtime import FakeSerial, port

ID = '00000000-0000-4000-8000-000000000001'


class CompletionVoiceTests(unittest.TestCase):
    def task(self, **changes):
        return dict(dict(id=ID, title='界面任务', state='done', done_key='a'*16,
                         completed_at=100, result_hint='不可外发的完成正文'), **changes)

    def test_only_explicit_recent_completions_no_result_content(self):
        result = completion_events([self.task()], 101)
        self.assertEqual(result, [dict(id=ID, title='界面任务', key='a'*16, completed_at=100)])
        for state in ['running', 'unknown', 'interrupted', 'needs_input']:
            self.assertEqual(completion_events([self.task(state=state)], 101), [])
        for at in [69, 102, float('nan'), float('inf'), True, None, '100']:
            self.assertEqual(completion_events([self.task(completed_at=at)], 101), [])
        for data in [dict(done_key=''), dict(done_key='old'), dict(id='invalid')]:
            self.assertEqual(completion_events([self.task(**data)], 101), [])
        self.assertEqual(completion_events([self.task(state='running')]*8+[self.task()], 101), [])

    def test_real_tracker_completion_key_changes_and_abort_is_not_completion(self):
        tracker = Tracker()
        def event(kind, turn, at):
            tracker.accept(dict(type='event_msg', timestamp=dt.datetime.fromtimestamp(at,dt.timezone.utc).isoformat(),
                                payload=dict(type=kind,turn_id=turn)))
        event('task_started','a',100);event('task_complete','a',101)
        first=tracker.notification_keys(102)[0]
        self.assertTrue(completion_events([self.task(done_key=first,completed_at=tracker.completed_at,state=tracker.current(102))],102))
        event('task_started','b',103);event('turn_aborted','b',104)
        self.assertEqual(completion_events([self.task(done_key=first,completed_at=101,state=tracker.current(104))],104),[])
        event('task_started','c',105);event('task_complete','c',106)
        self.assertNotEqual(first,tracker.notification_keys(107)[0])

    def test_runtime_feed_and_data_failure_clear_without_robot_protocol_change(self):
        now=time.time()
        current=[self.task(completed_at=now-1)]
        source=SimpleNamespace(snapshot=lambda:current)
        serial=FakeSerial()
        with tempfile.TemporaryDirectory() as directory:
            bridge=Bridge(source,directory,serial_factory=lambda:serial,port_provider=lambda:[port()])
            bridge.step()
            status=json.loads((Path(directory)/'status.json').read_text())
            self.assertEqual(status['completion_events'][0]['title'],'界面任务')
            self.assertNotIn('不可外发的完成正文',json.dumps(status,ensure_ascii=False))
            self.assertTrue(serial.packets[-1].startswith(b'SC5'))
            source.snapshot=lambda:(_ for _ in ()).throw(sqlite3.OperationalError())
            bridge.step()
            status=json.loads((Path(directory)/'status.json').read_text())
            self.assertEqual(status['completion_events'],[])
            self.assertEqual(status['data_source'],'unavailable')
            bridge.disconnect()


if __name__ == '__main__':
    unittest.main()
