"""会话来源 → 实际任务列表 → 设备通知包的回归，隔离数据库与假串口。"""
import datetime as dt
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from monitor import Tracker, recent_tasks
from runtime import Bridge, NotificationGate, TaskSource
from test_monitor import event, ask, reply
from test_runtime import FakeSerial, port

PARENT = '00000000-0000-0000-0000-000000000001'


def stamped(kind, turn, at):
    value = event(kind, turn)
    value['timestamp'] = dt.datetime.fromtimestamp(at, dt.timezone.utc).isoformat()
    return value


class SessionNotificationTests(unittest.TestCase):
    def test_internal_threads_excluded_before_candidate_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'state_1.sqlite'
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute('CREATE TABLE threads(id,rollout_path,name,title,updated_at,archived,agent_path,source,thread_source)')
                conn.execute('INSERT INTO threads VALUES(?,?,?,?,?,?,?,?,?)',
                             (PARENT, 'parent.jsonl', '', '主会话', 10, 0, None, 'vscode', 'user'))
                sources = [('{"subagent":{"other":"guardian"}}', 'guardian_review'),
                           ('{ "subagent": {"thread_spawn": {"depth":1}}}', None),
                           ('vscode', 'subagent'), ('vscode', 'guardian_review')]
                for i in range(40):
                    source, provenance = sources[i % len(sources)]
                    conn.execute('INSERT INTO threads VALUES(?,?,?,?,?,?,?,?,?)',
                                 (str(i), 'internal.jsonl', '', '内部检查', 100+i, 0, None, source, provenance))
            rows = recent_tasks(db, '1')
            self.assertEqual([r[0] for r in rows], [PARENT])

    def test_legacy_source_column_and_noninternal_user_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'state_1.sqlite'
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute('CREATE TABLE threads(id,rollout_path,name,title,updated_at,archived,agent_path,source)')
                for i, source in enumerate(('cli', 'exec', 'vscode', None, '{"subagent":{"other":"guardian"}}', 'subagent', '{broken')):
                    conn.execute('INSERT INTO threads VALUES(?,?,?,?,?,?,?,?)', (str(i),'x','','会话',i,0,None,source))
            self.assertEqual([r[0] for r in recent_tasks(db,None)], ['3','2','1','0'])

    def test_pending_question_completion_never_becomes_a_done_notice(self):
        tracker=Tracker();tracker.accept(event('task_started'));ask(tracker)
        tracker.accept(event('task_complete'))
        self.assertEqual(tracker.current(), 'needs_input')
        self.assertEqual(tracker.notification_keys(time.time()+2)[0], '')
        reply(tracker)
        self.assertEqual(tracker.notification_keys(time.time()+2)[0], '')

    def test_same_turn_completion_is_idempotent(self):
        tracker=Tracker();tracker.accept(stamped('task_started','a',100))
        tracker.accept(stamped('task_complete','a',101));key=tracker.notification_keys(103)[0]
        self.assertTrue(key)
        tracker.accept(stamped('task_complete','a',110))
        self.assertEqual(tracker.notification_keys(112)[0], key)
        self.assertEqual(tracker.completed_at, 101)
        tracker.accept(stamped('task_started','b',120))
        tracker.accept(stamped('task_complete','a',121))
        self.assertEqual(tracker.notification_keys(122)[0], '')
        self.assertEqual(tracker.current(122), 'running')

    def test_brief_completion_cannot_notify_before_queued_continuation(self):
        tracker=Tracker();tracker.accept(stamped('task_started','a',100))
        tracker.accept(stamped('task_complete','a',101))
        self.assertEqual(tracker.notification_keys(101.01)[0], '')
        tracker.accept(stamped('task_started','b',101.02))
        self.assertEqual(tracker.notification_keys(103)[0], '')
        tracker.accept(stamped('task_complete','b',104))
        self.assertTrue(tracker.notification_keys(106)[0])

    def test_reconnect_during_settling_never_replays_old_completion(self):
        tracker=Tracker();tracker.accept(stamped('task_started','a',100))
        tracker.accept(stamped('task_complete','a',101))
        gate=NotificationGate()
        def snapshot(at):
            return dict(id=PARENT,state=tracker.current(at),done_key=tracker.notification_keys(at)[0],
                        wait_key='',completed_at=tracker.completed_at)
        self.assertEqual(gate.filter([snapshot(101.1)])[0]['done_key'], '')
        self.assertEqual(gate.filter([snapshot(103)])[0]['done_key'], '')
        tracker.accept(stamped('task_started','b',104));tracker.accept(stamped('task_complete','b',105))
        self.assertTrue(gate.filter([snapshot(107)])[0]['done_key'])

    def test_real_source_and_wire_exclude_guardian_and_old_done_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);db=root/'state_1.sqlite';parent=root/'parent.jsonl';guardian=root/'guardian.jsonl'
            now=time.time()
            parent.write_text(json.dumps(stamped('task_started','a',now-10))+'\n')
            guardian.write_text(json.dumps(stamped('task_started','child',now-10))+'\n')
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute('CREATE TABLE threads(id,rollout_path,name,title,updated_at,archived,agent_path,source,thread_source)')
                conn.executemany('INSERT INTO threads VALUES(?,?,?,?,?,?,?,?,?)', [
                    (PARENT,str(parent),'','主会话',1,0,None,'vscode','user'),
                    ('00000000-0000-0000-0000-000000000002',str(guardian),'','内部检查',2,0,None,'{"subagent":{"other":"guardian"}}','guardian_review')])
            source=TaskSource(root);serial=FakeSerial()
            bridge=Bridge(source,root/'runtime',serial_factory=lambda:serial,port_provider=lambda:[port()])
            try:
                bridge.step()
                with guardian.open('a') as f:f.write(json.dumps(stamped('task_complete','child',now-2))+'\n')
                bridge.step()
                self.assertEqual([t['id'] for t in bridge.tasks], [PARENT])
                self.assertFalse(any(t['done_key'] for t in bridge.tasks))
                # 一次读到结束和立即继续时，不携带上一轮的完成标记。
                with parent.open('a') as f:
                    for kind,turn,at in [('task_complete','a',now-2),('task_started','b',now-1.9)]:
                        f.write(json.dumps(stamped(kind,turn,at))+'\n')
                bridge.step()
                fields=serial.packets[-1].decode().strip().split('\t')
                self.assertEqual((fields[9],fields[11]), ('running','-'))
                with parent.open('a') as f:f.write(json.dumps(stamped('task_complete','b',now-1.5))+'\n')
                bridge.step()
                fields=serial.packets[-1].decode().strip().split('\t')
                self.assertEqual(fields[9], 'done');self.assertNotEqual(fields[11], '-')
                state=json.loads((root/'runtime/status.json').read_text())
                self.assertEqual([e['id'] for e in state['completion_events']], [PARENT])
            finally:bridge.disconnect()


if __name__ == '__main__':unittest.main()
