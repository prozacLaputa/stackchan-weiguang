import json
import unittest
from monitor import Tracker, sync_packet
from waiting_reason import clean_reason, summarize_question
from test_monitor import item, event, reply


class WaitingReasonTests(unittest.TestCase):
    def ask(self, tracker, questions, call='q', accepted=True):
        tracker.accept(item('function_call', name='functions.request_user_input_async',
                            call_id=call, arguments=json.dumps({'questions':questions})))
        if accepted:
            tracker.accept(item('function_call_output', call_id=call, output='{"accepted":true}'))

    def test_short_header_and_actual_question_instead_of_background(self):
        self.assertEqual(summarize_question({'header':'提醒强度','question':'在工位上更喜欢哪种？','options':[{},{}]}),'待选择：提醒强度')
        self.assertEqual(summarize_question({'title':'新版已刷好。你更喜欢哪种提醒强度？'}),'待答：你更喜欢哪种提醒强度')
        self.assertEqual(summarize_question({'title':'记录已开始。请把亮度调成柔和。完成后告诉我。'}),'待答：请把亮度调成柔和')

    def test_only_acknowledged_unanswered_question_shown(self):
        t=Tracker();t.accept(event('task_started'))
        self.ask(t,[{'title':'选哪种提醒？'}],accepted=False)
        self.assertEqual(t.waiting_reason(),'')
        t.accept(item('function_call_output',call_id='q',output='{"accepted":true}'))
        self.assertEqual(t.waiting_reason(),'待答：选哪种提醒')
        t.accept(event('task_complete'))
        self.assertEqual(t.waiting_reason(),'待答：选哪种提醒')
        reply(t,'q')
        self.assertEqual(t.waiting_reason(),'')

    def test_partial_reply_moves_to_remaining_question_without_new_notice_key(self):
        t=Tracker();t.accept(event('task_started'))
        self.ask(t,[{'title':'先选颜色？'},{'title':'再选大小？'}])
        key=t.notification_keys()[1]
        self.assertEqual(t.waiting_reason(),'待答：先选颜色')
        reply(t,'q',0)
        self.assertEqual(t.waiting_reason(),'待答：再选大小')
        self.assertEqual(t.notification_keys()[1],key)
        reply(t,'q',1);self.assertEqual(t.waiting_reason(),'')

    def test_latest_accepted_call_and_clearing_on_direction_or_new_turn(self):
        t=Tracker();t.accept(event('task_started'))
        self.ask(t,[{'title':'第一项？'}],'first')
        self.ask(t,[{'title':'第二项？'}],'second',accepted=False)
        self.assertEqual(t.waiting_reason(),'待答：第一项')
        t.accept(item('function_call_output',call_id='second',output='{"accepted":true}'))
        self.assertEqual(t.waiting_reason(),'待答：第二项')
        reply(t,'second');self.assertEqual(t.waiting_reason(),'待答：第一项')
        t.accept(item('message',role='user',content=[{'text':'暂时不做'}]));self.assertEqual(t.waiting_reason(),'')
        self.ask(t,[{'title':'继续吗？'}]);t.accept(event('task_started','next'));self.assertEqual(t.waiting_reason(),'')

    def test_blocking_request_and_failed_async_clear(self):
        t=Tracker()
        t.accept(item('function_call',name='functions.request_user_input',call_id='sync',arguments=json.dumps({'questions':[{'header':'界面风格','question':'请选择'}]})))
        self.assertEqual(t.waiting_reason(),'待答：界面风格')
        t.accept(item('function_call_output',call_id='sync',output='{}'));self.assertEqual(t.waiting_reason(),'')
        self.ask(t,[{'title':'继续吗？'}],accepted=False)
        t.accept(item('function_call_output',call_id='q',output='{"accepted":false}'));self.assertEqual(t.waiting_reason(),'')

    def test_payload_is_short_single_line_and_excludes_answer_options_and_body(self):
        t=Tracker();secret='private_answer_not_for_robot'
        self.ask(t,[{'title':'请选择提醒方式？','body':secret,'answer':secret,'options':[secret]}])
        task=dict(id='a'*36,title='测试任务',state='needs_input',wait_reason=t.waiting_reason(),body=secret,answer=secret)
        packet=sync_packet(1,[task],True,1,1,0,False,True)
        self.assertNotIn(secret.encode(),packet)
        self.assertEqual(packet.count(b'\n'),1)
        self.assertEqual(len(packet.decode().strip().split('\t')),15)
        task['wait_reason']='\t\r\n\x00'+('长问题😀'*80)
        packet=sync_packet(2,[task]*8,True,1,1,0,False,True)
        self.assertLessEqual(len(packet),4096)
        self.assertEqual(len(packet.decode().strip().split('\t')),64)
        self.assertNotIn(b'\x00',packet)
        task['title']='😀'*60;task['wait_reason']='😀'*32
        self.assertLessEqual(len(sync_packet(3,[task]*8,True,86399,86399,604800,True,True)),4096)

    def test_reason_not_sent_for_answered_unavailable_or_legacy_snapshot(self):
        task=dict(id='a'*36,title='任务',state='needs_input',wait_reason='待答：选择颜色')
        self.assertTrue(sync_packet(1,[task],True,0,0,0,False).startswith(b'SC5'))
        self.assertNotIn('选择颜色'.encode(),sync_packet(1,[task],True,0,0,0,False))
        self.assertEqual(sync_packet(1,[task],False,0,0,0,False,True).decode().strip().split('\t')[-1],'-')
        task['state']='done'
        self.assertEqual(sync_packet(1,[task],True,0,0,0,False,True).decode().strip().split('\t')[-1],'-')

    def test_malformed_fields_and_markdown(self):
        for q in (None,{}, {'title':12}, {'header':'颜色','options':123}, {'title':'？'}):
            self.assertTrue(summarize_question(q))
        self.assertEqual(clean_reason('看看 [文档](https://example.com/private)\nhttps://example.com/token'), '看看 文档 链接')
        self.assertLessEqual(len(clean_reason('内容'*100)),32)


if __name__=='__main__':unittest.main()
