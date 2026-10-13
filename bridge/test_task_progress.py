import datetime as dt
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from monitor import Tracker, sync_packet
from runtime import Bridge, TaskSource
from task_progress import ProgressTracker, PROGRESS_TTL
from test_monitor import event, item, ask, reply
from test_runtime import FakeSerial, port

ID='00000000-0000-0000-0038-000000000001'


def message(text='正在编译固件。随后检查设置。', **kwargs):
    return dict(type='message', role='assistant', channel='commentary',
                content=[dict(type='output_text',text=text)], **kwargs)


def stamp(record, seconds):
    return dict(record,timestamp=dt.datetime.fromtimestamp(seconds,dt.timezone.utc).isoformat())


class ProgressTests(unittest.TestCase):
    def test_excerpt_is_visible_assistant_only(self):
        p=ProgressTracker()
        for change in (dict(role='user'),dict(role='developer'),dict(channel='analysis'),dict(channel='final'),
                       dict(recipient='functions.exec'),dict(type='function_call_output'),dict(channel=None),
                       dict(content=[dict(type='reasoning_text',text='hidden')])):
            p.accept(dict(message(),**change),100)
            self.assertFalse(p.current(101,'running'))
        p.accept(message(),102)
        self.assertEqual(p.current(102,'running'),'进展：正在编译固件。')
        p.accept(dict(message('现在检查设置保存。'),channel=None,phase='commentary'),103)
        self.assertEqual(p.current(103,'running'),'进展：现在检查设置保存。')
        p.accept(message('更早的进展。'),101)
        self.assertEqual(p.current(104,'running'),'进展：现在检查设置保存。')

    def test_bounded_markup_and_no_invented_stage(self):
        p=ProgressTracker()
        p.accept(message('## 进展\n> 引用他人的结果\n```sh\nsecret\n```\n**检查未通过**，还在排查 [设置](/private/path)。\n<oai-mem-citation>private</oai-mem-citation>'),100)
        self.assertEqual(p.current(101,'running'),'进展：检查未通过，还在排查 设置。')
        p.accept(message('内容😀\t'*100),102)
        text=p.current(103,'running')
        self.assertLessEqual(len(text),32);self.assertNotIn('\t',text)
        for value in ([],None,'bad',[{'type':'output_text','text':None}]):
            p=ProgressTracker();p.accept(dict(message(),content=value),100)
            self.assertFalse(p.current(100,'running'))

    def test_expiry_and_state_fallback(self):
        p=ProgressTracker();p.accept(message(),100)
        self.assertTrue(p.current(100+PROGRESS_TTL-1,'running'))
        self.assertFalse(p.current(100+PROGRESS_TTL,'running'))
        self.assertFalse(p.current(99,'running'))
        for state in ('unknown','interrupted','done','needs_input'):
            self.assertFalse(p.current(101,state))
        p.accept(message('只有最新的可见正文。'),101)
        p.accept(message('```\n只包含代码\n```'),102)
        self.assertFalse(p.current(103,'running'))

    def test_lifecycle_and_wait_priority(self):
        t=Tracker();t.accept(stamp(event('task_started'),100))
        t.accept(stamp(dict(type='response_item',payload=message()),101))
        self.assertTrue(t.progress.current(102,t.current(102)))
        ask(t)
        self.assertFalse(t.progress.current(102,t.current(102)))
        reply(t)
        self.assertTrue(t.progress.current(102,t.current(102)))
        t.accept(stamp(event('task_started','b'),103))
        self.assertFalse(t.progress.current(103,t.current(103)))
        t.accept(stamp(dict(type='response_item',payload=message()),104))
        t.accept(stamp(event('turn_aborted','b'),105));self.assertFalse(t.progress.hint)
        t.accept(stamp(event('task_started','c'),106))
        t.accept(stamp(dict(type='response_item',payload=message()),107))
        t.accept(stamp(dict(type='response_item',payload=dict(message('完成了。'),channel='final')),108))
        self.assertFalse(t.progress.hint)
        t.accept(stamp(event('task_complete','c'),109))
        self.assertEqual(t.result_hint,'摘录：完成了。')
        t.accept(stamp(dict(type='response_item',payload=message('晚到的消息。')),110))
        self.assertFalse(t.progress.hint)

    def test_steering_clears_previous_progress(self):
        t=Tracker();t.accept(stamp(event('task_started'),100))
        t.accept(stamp(dict(type='response_item',payload=message()),101))
        t.accept(stamp(item('message',role='user',content=[dict(type='input_text',text='先停一下，换个方案')]),102))
        self.assertFalse(t.progress.hint)

    def test_source_tail_multi_task_and_expiry(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);db=root/'state_1.sqlite'
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE threads (id TEXT,rollout_path TEXT,name TEXT,title TEXT,updated_at INTEGER,archived INTEGER,agent_path TEXT)')
                for i in range(2):
                    log=root/f'{i}.jsonl'
                    records=[stamp(event('task_started',str(i)),100),stamp(dict(type='response_item',payload=message(f'正在检查任务{i}。')),101)]
                    log.write_text(''.join(json.dumps(r)+'\n' for r in records))
                    conn.execute('INSERT INTO threads VALUES (?,?,?,?,?,0,NULL)',(ID[:-1]+str(i),str(log),'',f'任务{i}',i))
            source=TaskSource(root)
            with patch('time.time',return_value=102):
                rows=source.snapshot()
                self.assertEqual([r['progress_hint'] for r in rows],['进展：正在检查任务1。','进展：正在检查任务0。'])
            with patch('time.time',return_value=101+PROGRESS_TTL):
                rows=source.snapshot();self.assertTrue(all(r['state']=='running' and not r['progress_hint'] for r in rows))

    def test_protocol_old_firmware_fallback_and_payload_bound(self):
        task=dict(id=ID,title='😀'*60,state='running',progress_hint='😀'*32,wait_reason='待答：确认',result_hint='摘录：修改完毕')
        payload=sync_packet(1,[task]*8,True,86399,86399,604800,True,True,True,True)
        self.assertTrue(payload.startswith(b'SC8\t'));self.assertLess(len(payload),4096)
        self.assertEqual(len(payload.decode().strip().split('\t')),8+8*7)
        for state,ok,expected in [('running',True,'😀'*32),('done',True,'摘录：修改完毕'),('needs_input',True,'待答：确认'),('unknown',True,'-'),('interrupted',True,'-'),('running',False,'-')]:
            p=sync_packet(1,[dict(task,state=state)],ok,0,0,0,False,True,True,True)
            self.assertEqual(p.decode().strip().split('\t')[-1],expected)
        old=sync_packet(1,[task],True,0,0,0,False,True,True)
        self.assertTrue(old.startswith(b'SC7'));self.assertEqual(old.decode().strip().split('\t')[-1],'-')

    def test_runtime_progress_update_failure_and_no_log_content(self):
        tasks=[dict(id=ID,title='任务',state='running',progress_hint='进展：正在编译固件')]
        with tempfile.TemporaryDirectory() as root:
            link=FakeSerial();source=SimpleNamespace(snapshot=lambda:tasks)
            b=Bridge(source,root,serial_factory=lambda:link,port_provider=lambda:[port()])
            b.maintain_companion=lambda *args,**kwargs:None  # 本测试的串口只模拟任务 ACK。
            b.step();b.device_supported=True;b.device={'firmware':'0.37'};b.step()
            self.assertTrue(link.packets[-1].startswith(b'SC7'));self.assertNotIn('进展'.encode(),link.packets[-1])
            b.device={'firmware':'0.38'};b.step()
            self.assertTrue(link.packets[-1].startswith(b'SC8'));self.assertIn('正在编译'.encode(),link.packets[-1])
            b.device={'firmware':'0.39'}
            tasks[0]['progress_hint']='进展：正在检查保存';b.step()
            self.assertIn('正在检查保存'.encode(),link.packets[-1])
            self.assertNotIn('正在检查保存',(Path(root)/'status.json').read_text())
            tasks[0]['progress_hint']='';b.step();self.assertEqual(link.packets[-1].decode().strip().split('\t')[-1],'-')
            tasks[0]['progress_hint']='进展：再次检查';b.step()
            source.snapshot=lambda:(_ for _ in ()).throw(sqlite3.OperationalError())
            b.step();self.assertFalse(b.tasks[0]['progress_hint']);self.assertNotIn('进展'.encode(),link.packets[-1])
            b.disconnect()

if __name__=='__main__':unittest.main()
