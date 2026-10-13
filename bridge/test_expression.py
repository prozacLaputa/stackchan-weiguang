import unittest
from expression import classify, visible_text, ExpressionTracker
from monitor import Tracker, batch_packet
from test_monitor import item, event
import datetime as dt


def message(text, role='user', phase=None):
    return dict(type='message', role=role, phase=phase,
                content=[dict(type='input_text' if role == 'user' else 'output_text', text=text)])


class ExpressionTests(unittest.TestCase):
    def test_clear_cues(self):
        for text, mood in [('还是不行，刚才又报错了', 'curious'), ('这个问题解决了', 'joy'),
                           ('现在我很满意', 'joy'), ('先讨论一下方案', 'thinking'),
                           ('为什么还是这样', 'thinking'), ('我先编译固件并运行测试', 'focus'),
                           ('接下来开始实现它', 'focus'), ('今天吃什么', None)]:
            with self.subTest(text=text): self.assertEqual(classify(text), mood)

    def test_hypotheticals_negation_and_feature_discussion(self):
        for text in ['如果成功了就告诉我', '比如遇到报错了应该怎么办', '问题还没有解决了似的感觉',
                     '我不满意', '尚未修复', '测试用例要覆盖测试通过', '成功了以后显示开心表情',
                     '不再测试通过之后抬头', '我没有说这个问题解决了']:
            with self.subTest(text=text): self.assertIsNone(classify(text))
        self.assertEqual(classify('编译通过了，但是运行时还是不行'), 'curious')
        self.assertEqual(classify('测试通过了，但是还在报错'), 'curious')
        self.assertEqual(classify('我先运行测试，确认聊天能触发表情'), 'focus')

    def test_only_visible_chat_and_no_tool_or_analysis(self):
        for role, phase in [('system', None), ('developer', None), ('assistant', 'analysis'), ('assistant', None)]:
            self.assertEqual(visible_text(message('问题解决了', role, phase)), '')
        for phase in ('commentary', 'final_answer'):
            self.assertEqual(classify(visible_text(message('问题解决了', 'assistant', phase))), 'joy')
        self.assertEqual(visible_text(dict(type='function_call_output', output='问题解决了')), '')

    def test_context_code_and_examples_removed(self):
        for text in ['# AGENTS.md instructions\n问题解决了', '<environment_context>问题解决了</environment_context>',
                     '<external_codex_apps_open_page>问题解决了</external_codex_apps_open_page>',
                     '<send_user_message_question_reply>问题解决了</send_user_message_question_reply>',
                     '```python\n问题解决了\n```', '> 问题解决了', '|问题解决了|', '`问题解决了`']:
            self.assertIsNone(classify(visible_text(message(text))))
        text='<in-app-browser-context>问题解决了</in-app-browser-context>\n我先编译固件'
        self.assertEqual(classify(visible_text(message(text))), 'focus')

    def test_hold_expiry_and_clock(self):
        t=ExpressionTracker();t.accept(message('我先编译固件'),100)
        t.accept(message('为什么会这样'),102);self.assertEqual(t.current(103,'running'),'focus')
        self.assertEqual(t.current(103,'done'),'idle')
        t.accept(message('为什么会这样'),105);self.assertEqual(t.current(106,'running'),'thinking')
        self.assertEqual(t.current(141,'running'),'idle')
        self.assertEqual(t.current(104,'running'),'idle')
        self.assertEqual(t.current(110,'unknown'),'idle')
        t.accept(message('太好了'),110);t.accept(message('还是不行'),111)
        self.assertEqual(t.current(112,'running'),'curious')
        t.accept(message('太好了'),99);self.assertEqual(t.mood,'curious')
        self.assertEqual(t.current(127,'done'),'idle')

    def test_no_raw_text_saved_or_transmitted(self):
        secret='正文不应发送到机器人';t=ExpressionTracker();t.accept(message('我先编译固件 '+secret),100)
        self.assertEqual(set(vars(t)), {'mood','at'})
        data=batch_packet(1,[dict(id='a'*36,title='任务',state='running',mood=t.mood,body=secret)])
        self.assertNotIn(secret.encode(),data);self.assertIn(b'focus',data)
        malformed=batch_packet(1,[dict(id='a'*36,title='任务',state='running',mood='joy\nMOTION_ON')])
        self.assertNotIn(b'MOTION',malformed);self.assertEqual(malformed.count(b'\n'),1)

    def test_new_turn_abort_and_independent_tasks(self):
        t=Tracker();t.accept(event('task_started'))
        t.accept(item('message',**{k:v for k,v in message('问题解决了').items() if k!='type'}))
        self.assertEqual(t.expression.mood,'joy')
        self.assertEqual(Tracker().expression.mood,'idle')
        t.accept(event('turn_aborted'));self.assertEqual(t.expression.mood,'idle')
        t.expression.accept(message('问题解决了'),100)
        t.accept(event('task_started','b'));self.assertEqual(t.expression.mood,'idle')

    def test_current_input_just_before_turn_is_kept(self):
        t=Tracker();now=dt.datetime.now(dt.timezone.utc)
        r=item('message',**{k:v for k,v in message('我先编译固件').items() if k!='type'})
        r['timestamp']=now.isoformat();t.accept(r)
        r=event('task_started');r['timestamp']=(now+dt.timedelta(seconds=1)).isoformat();t.accept(r)
        self.assertEqual(t.expression.mood,'focus')


if __name__ == '__main__': unittest.main()
