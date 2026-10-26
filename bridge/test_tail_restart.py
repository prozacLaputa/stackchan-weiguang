"""重启时当前轮次开始事件位于常规尾部窗口之外的回归。"""
import json
from pathlib import Path
import tempfile
import time
import unittest

from monitor import Tail
from test_monitor import event, item


class TailRestartTests(unittest.TestCase):
    def replay(self, records, expected):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'rollout.jsonl'
            path.write_text(''.join(json.dumps(r) + '\n' for r in records))
            tail = Tail(path)
            self.assertEqual(tail.poll(), expected)
            self.assertEqual(tail.poll(), expected)
            self.assertEqual(tail.offset, path.stat().st_size)
            return tail.tracker

    def noise(self):
        # 大工具输出跨过 2 MB 边界；内容并非生命周期信号。
        return item('function_call_output', call_id='work', output='x' * 2_100_000)

    def test_restart_keeps_long_turn_running(self):
        self.replay([event('task_started'), self.noise(), item('reasoning')], 'running')

    def test_restart_recovers_pending_question_before_window(self):
        tracker = self.replay([
            event('task_started'),
            item('function_call', name='request_user_input_async', call_id='q',
                 arguments=json.dumps({'questions': [{'title': '请选择'}]})),
            item('function_call_output', call_id='q', output='{"accepted":true}'),
            self.noise(), item('reasoning')], 'needs_input')
        self.assertTrue(tracker.notification_keys()[1])

    def test_known_terminal_state_does_not_scan_older_history(self):
        from unittest.mock import patch
        with patch.object(Tail, '_turn_start_before', side_effect=AssertionError('不应回溯')):
            self.replay([event('task_started'), self.noise(), event('task_complete')], 'done')

    def test_restored_old_completion_does_not_become_fresh(self):
        complete = event('task_complete')
        complete['timestamp'] = '2020-01-01T00:00:00+00:00'
        tracker = self.replay([event('task_started'), complete, self.noise(), item('reasoning')], 'done')
        self.assertEqual(tracker.notification_keys(time.time())[0], '')

    def test_no_start_is_not_inferred_from_text_or_tool_activity(self):
        self.replay([item('message', role='assistant', content=[{'text': 'task_started'}]),
                     self.noise(), item('reasoning')], 'unknown')

    def test_partial_record_remains_incremental_after_restore(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'rollout.jsonl'
            prefix = ''.join(json.dumps(r) + '\n' for r in [event('task_started'), self.noise()])
            final = json.dumps(event('task_complete'))
            path.write_text(prefix + final[:30])
            tail = Tail(path)
            self.assertEqual(tail.poll(), 'running')
            with path.open('a') as f:
                f.write(final[30:] + '\n')
            self.assertEqual(tail.poll(), 'done')


if __name__ == '__main__':
    unittest.main()
