import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from completion_summary import summarize_completion
from monitor import Tracker, sync_packet
from runtime import Bridge
from task_actions import pending_tasks, resolve_pending
from test_monitor import event, item, ask, reply
from test_runtime import FakeSerial, port

ID='00000000-0000-0000-0046-000000000001'


class ResultTests(unittest.TestCase):
    def finish(self,t,text='',turn='a'):
        e=event('task_complete',turn)
        e['payload']['last_agent_message']=text
        t.accept(e)

    def test_actual_final_only_and_new_turn_clears(self):
        t=Tracker();t.accept(event('task_started'))
        t.accept(item('message',role='assistant',channel='commentary',content=[{'text':'已经全部完成'}]))
        self.assertFalse(t.result_hint)
        t.accept(item('message',role='assistant',channel='final',content=[{'text':'改动已完成，仍有两项测试失败。'}]))
        self.assertFalse(t.result_hint)
        self.finish(t)
        self.assertEqual(t.result_hint,'摘录：改动已完成，仍有两项测试失败。')
        t.accept(event('task_started','b'));self.assertFalse(t.result_hint)
        self.finish(t,'旧轮的回复','a');self.assertFalse(t.result_hint)
        t.accept(event('turn_aborted','b'));self.assertFalse(t.result_hint)

    def test_completion_event_and_outstanding_question(self):
        t=Tracker();t.accept(event('task_started'));ask(t)
        self.finish(t,'仅完成了方案，尚未实施。')
        self.assertEqual(t.current(),'needs_input')
        task=dict(id=ID,title='任务',state=t.current(),wait_reason=t.waiting_reason(),result_hint=t.result_hint)
        self.assertIn('待答'.encode(),sync_packet(1,[task],True,0,0,0,False,True,True))
        self.assertNotIn('尚未实施'.encode(),sync_packet(1,[task],True,0,0,0,False,True,True))
        reply(t);self.assertEqual(t.current(),'done')
        self.assertEqual(t.result_hint,'摘录：仅完成了方案，尚未实施。')

    def test_plain_excerpt_no_success_classification_or_markup(self):
        self.assertEqual(summarize_completion('## 结果\n\n**测试未通过**，需要修复。\n下一步另述。'),'摘录：测试未通过，需要修复。')
        self.assertEqual(summarize_completion('```sh\nsecret command\n```\n已更新 [文档](/private/path.md)。\n<oai-mem-citation>private</oai-mem-citation>'),'摘录：已更新 文档。')
        for value in (None,42,{},'','## 结果\n```secret```'):
            self.assertEqual(summarize_completion(value),'')
        excerpt=summarize_completion('内容😀\t'*100)
        self.assertLessEqual(len(excerpt),32);self.assertNotIn('\t',excerpt)

    def test_legacy_offline_active_and_max_payload(self):
        task=dict(id=ID,title='😀'*60,state='done',result_hint='😀'*32,wait_reason='old')
        self.assertNotIn('😀'*32,sync_packet(1,[dict(task,title='任务')],True,0,0,0,False,True).decode())
        payload=sync_packet(2,[task]*8,True,86399,86399,604800,True,True,True)
        self.assertTrue(payload.startswith(b'SC7\t'));self.assertLess(len(payload),4096)
        for state,ok in [('running',True),('unknown',True),('interrupted',True),('done',False)]:
            packet=sync_packet(3,[dict(task,state=state)],ok,0,0,0,False,True,True)
            self.assertEqual(packet.decode().strip().split('\t')[-1],'-')

    def test_runtime_negotiates_result_and_clears_on_source_failure(self):
        import sqlite3
        task=dict(id=ID,title='微光',state='done',result_hint='摘录：界面已修改',done_key='old')
        current=[task];serial=FakeSerial()
        with tempfile.TemporaryDirectory() as root:
            source=SimpleNamespace(snapshot=lambda:current)
            b=Bridge(source,root,serial_factory=lambda:serial,port_provider=lambda:[port()])
            b.step();self.assertTrue(serial.packets[-1].startswith(b'SC5'))
            b.device_supported=True;b.device={'firmware':'0.29'};b.step()
            self.assertTrue(serial.packets[-1].startswith(b'SC7'))
            self.assertIn('界面已修改'.encode(),serial.packets[-1])
            task.update(state='needs_input',wait_reason='待答：是否继续')
            b.step();status=json.loads((Path(root)/'status.json').read_text())
            self.assertEqual(status['pending_tasks'][0]['id'],ID)
            self.assertNotIn('result_hint',status['pending_tasks'][0])
            source.snapshot=lambda:(_ for _ in ()).throw(sqlite3.OperationalError())
            b.step();status=json.loads((Path(root)/'status.json').read_text())
            self.assertEqual(status['pending_tasks'],[])
            self.assertEqual(serial.packets[-1].decode().strip().split('\t')[-1],'-')
            b.disconnect()


class TaskActionTests(unittest.TestCase):
    def test_only_current_pending_top8_and_valid_ids(self):
        task=dict(id=ID,title='任务',state='needs_input',wait_reason='待答：是否继续')
        self.assertEqual(pending_tasks([task])[0]['reason'],'待答：是否继续')
        source=SimpleNamespace(snapshot=lambda:[task])
        self.assertEqual(resolve_pending(source,ID),dict(ok=True,thread_id=ID))
        task['state']='done';self.assertEqual(resolve_pending(source,ID)['error'],'no_longer_waiting')
        self.assertEqual(pending_tasks([dict(task,state='needs_input',id='https://host/path')]),[])
        task['state']='needs_input'
        self.assertEqual(pending_tasks([dict(task,state='running')]*8+[task]),[])
        source.snapshot=lambda:[]
        self.assertEqual(resolve_pending(source,ID)['error'],'no_longer_waiting')

    def test_invalid_id_never_reads_source(self):
        def read():raise AssertionError('invalid id must not access data')
        for value in (None,'','../../config.json','codex://threads/'+ID,ID+'?x=1'):
            self.assertEqual(resolve_pending(SimpleNamespace(snapshot=read),value)['error'],'invalid_thread')


if __name__=='__main__':unittest.main()
