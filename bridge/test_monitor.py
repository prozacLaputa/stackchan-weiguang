import datetime as dt
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from monitor import Tracker, Tail, packet, choose_tasks, recent_tasks, batch_packet

def event(kind, turn='a'):
    return {'timestamp':dt.datetime.now(dt.timezone.utc).isoformat(),'type':'event_msg','payload':{'type':kind,'turn_id':turn}}

def item(kind, **fields):
    return {'timestamp':dt.datetime.now(dt.timezone.utc).isoformat(),'type':'response_item',
            'payload':dict(type=kind, **fields)}

def ask(t, call='question-a', count=1, sync=False, accepted=True):
    name='request_user_input' if sync else 'request_user_input_async'
    t.accept(item('function_call', name='functions.'+name, call_id=call,
                  arguments=json.dumps({'questions':[{'title':'选择提示强度'}]*count})))
    if not sync:
        t.accept(item('function_call_output', call_id=call, output=json.dumps({'accepted':accepted})))

def reply(t, call='question-a', index=0):
    data=[{'questionItemId':json.dumps(['request_user_input_async',call,index]),'answer':'柔和'}]
    t.accept(item('message',role='user',content=[{'type':'input_text','text':
        '<send_user_message_question_reply>\n'+json.dumps(data)+'\n</send_user_message_question_reply>'}]))

class QuestionTests(unittest.TestCase):
    def test_async_waits_for_ack_and_clears_on_answer(self):
        t=Tracker();t.accept(event('task_started'))
        t.accept(item('function_call',name='request_user_input_async',call_id='q',
                      arguments='{"questions":[{"title":"选择"}]}'))
        self.assertEqual(t.current(),'running')
        t.accept(item('function_call_output',call_id='q',output='{"accepted":true}'))
        self.assertEqual(t.current(),'needs_input')
        reply(t,'q');self.assertEqual(t.current(),'running')

    def test_unanswered_can_outlive_turn_and_partial_answers(self):
        t=Tracker();t.accept(event('task_started'));ask(t,count=2)
        t.accept(event('task_complete'));self.assertEqual(t.current(time.time()+999),'needs_input')
        reply(t,'unrelated');self.assertEqual(t.current(),'needs_input')
        reply(t,index=1);self.assertEqual(t.current(),'needs_input')
        reply(t,index=1);self.assertEqual(t.current(),'needs_input')
        reply(t,index=0);self.assertEqual(t.current(),'done')

    def test_multiple_calls_and_blocking_request(self):
        t=Tracker();t.accept(event('task_started'));ask(t,call='a');ask(t,call='b',sync=True)
        reply(t,'a');self.assertEqual(t.current(),'needs_input')
        t.accept(item('function_call_output',call_id='b',output='{"answers":{}}'))
        self.assertEqual(t.current(),'running')

    def test_failed_request_does_not_wait(self):
        for output in ('{"accepted":false}','tool failed','{"isError":true}'):
            t=Tracker();t.accept(event('task_started'));ask(t)
            t.accept(item('function_call_output',call_id='question-a',output=output))
            self.assertEqual(t.current(),'running')

    def test_user_direction_new_turn_and_abort_clear(self):
        t=Tracker();t.accept(event('task_started'));ask(t)
        t.accept(item('message',role='user',content=[{'text':'保持柔和就行'}]))
        self.assertEqual(t.current(),'running')
        ask(t);t.accept(event('turn_aborted','old'));self.assertEqual(t.current(),'needs_input')
        t.accept(event('turn_aborted'));self.assertEqual(t.current(),'interrupted')
        ask(t);t.accept(event('task_started','b'));self.assertEqual(t.current(),'running')

    def test_ambient_context_and_assistant_text_are_not_answers(self):
        t=Tracker();t.accept(event('task_started'));ask(t)
        for role,text in [('assistant','好的'),('user','<environment_context>info</environment_context>'),
                          ('user','<external_codex_apps_open_page>context</external_codex_apps_open_page>')]:
            t.accept(item('message',role=role,content=[{'text':text}]))
            self.assertEqual(t.current(),'needs_input')

    def test_no_inference_from_text_or_malformed_events(self):
        t=Tracker();t.accept(event('task_started'))
        t.accept(item('message',role='assistant',content=[{'text':'请你确认 request_user_input_async'}]))
        t.accept(item('function_call',name='exec_command',call_id='x',arguments='request_user_input'))
        for args in ('bad','null','[]','{"questions":"not a list"}'):
            t.accept(item('function_call',name='request_user_input_async',call_id='q',arguments=args))
        self.assertEqual(t.current(),'running')
        ask(t)
        t.accept(item('message',role='user',content=[{'text':'<send_user_message_question_reply>broken'}]))
        self.assertEqual(t.current(),'needs_input')

class StatusTests(unittest.TestCase):
    def test_completion_identity_is_fresh_and_not_inferred(self):
        t=Tracker();t.accept(event('task_started'))
        t.accept(event('task_complete','old'));self.assertEqual(t.notification_keys()[0],'')
        t.accept(event('task_complete'));key=t.notification_keys(time.time()+2)[0]
        self.assertEqual(len(key),16)
        self.assertEqual(t.notification_keys(time.time()+31)[0],'')
        t.accept(event('task_started','b'));t.accept(event('task_complete','b'))
        self.assertNotEqual(t.notification_keys(time.time()+2)[0],key)

    def test_partial_answers_do_not_retrigger_waiting(self):
        t=Tracker();t.accept(event('task_started'));ask(t,call='a');ask(t,call='b')
        key=t.notification_keys()[1]
        reply(t,'b');self.assertEqual(t.notification_keys()[1],key)
        reply(t,'a');self.assertEqual(t.notification_keys()[1],'')
        ask(t,call='c');self.assertNotEqual(t.notification_keys()[1],key)
    def test_lifecycle_and_old_turn(self):
        t=Tracker(); t.accept(event('task_started')); self.assertEqual(t.current(),'running')
        t.accept(event('task_complete','old')); self.assertEqual(t.current(),'running')
        t.accept(event('task_complete')); self.assertEqual(t.current(),'done')
        t.accept(event('task_started','b')); t.accept(event('turn_aborted','b'))
        self.assertEqual(t.current(),'interrupted')
    def test_stale_running_is_unknown(self):
        t=Tracker();t.accept(event('task_started'))
        self.assertEqual(t.current(time.time()+301),'unknown')
    def test_partial_record_and_rotation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'events'; raw=json.dumps(event('task_started')).encode()
            p.write_bytes(raw[:20]); tail=Tail(p);self.assertEqual(tail.poll(),'unknown')
            with p.open('ab') as f:f.write(raw[20:]+b'\n')
            self.assertEqual(tail.poll(),'running')
            p.unlink();p.write_text(json.dumps(event('task_complete'))+'\n')
            self.assertEqual(tail.poll(),'done')
    def test_protocol_sanitizes_title(self):
        data=packet(1,'running','中文\n名字\t测试')
        self.assertEqual(data.count(b'\n'),1);self.assertEqual(data.count(b'\t'),3)
        self.assertIn('中文 名字 测试',data.decode())

class MultiTests(unittest.TestCase):
    def test_recent_top_eight_ignores_old_preferred_and_status_priority(self):
        tasks=[dict(id=str(i),state='done',title='任务',updated=i) for i in range(12)]
        tasks[1]['state']='running';tasks[2]['state']='needs_input'
        result=choose_tasks(tasks,'0')
        self.assertEqual([t['id'] for t in result],['11','10','9','8','7','6','5','4'])
        tasks[2]['updated']=20
        self.assertEqual([t['id'] for t in choose_tasks(tasks,'0')],['2','11','10','9','8','7','6','5'])

    def test_packet_keeps_question_content_private(self):
        pending=dict(id='q',state='needs_input',title='任务',question='private question',answer='private answer')
        self.assertEqual(batch_packet(5,[pending]),'SC4\t5\t1\tq\tneeds_input\t任务\t-\t-\tidle\n'.encode())

    def test_equal_activity_stable_and_fewer_than_eight(self):
        tasks=[dict(id=tid,state='running',title='任务',updated=10) for tid in ('c','a','b')]
        self.assertEqual([t['id'] for t in choose_tasks(tasks,'c')],['a','b','c'])
        self.assertEqual(choose_tasks(tasks,'c'),choose_tasks(list(reversed(tasks)),'a'))
        self.assertEqual(choose_tasks([],None),[])

    def test_archived_and_subagent_never_reenter_as_preferred(self):
        with tempfile.TemporaryDirectory() as root:
            db=Path(root)/'state.sqlite'
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute('CREATE TABLE threads(id TEXT,rollout_path TEXT,name TEXT,title TEXT,updated_at INTEGER,archived INTEGER,agent_path TEXT)')
                conn.executemany('INSERT INTO threads VALUES(?,?,?,?,?,?,?)',[
                    ('b','b.jsonl','','任务 B',10,0,None),('a','a.jsonl','','任务 A',10,0,None),
                    ('archived','archived.jsonl','','旧任务',30,1,None),
                    ('child','child.jsonl','','子任务',40,0,'/root/child')])
            for preferred in ('archived','child',None):
                self.assertEqual([r[0] for r in recent_tasks(db,preferred)],['a','b'])
    def test_batch_with_chinese_and_empty(self):
        tasks=[dict(id='a'*36,state='running',title='长任务\t中文\n标题'*20)]*8
        data=batch_packet(4,tasks)
        self.assertLess(len(data),4096)
        self.assertEqual(len(data.decode().strip().split('\t')),51)
        self.assertEqual(batch_packet(1,[]),b'SC4\t1\t0\n')

if __name__=='__main__':unittest.main()
