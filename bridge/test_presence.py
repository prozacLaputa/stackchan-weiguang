import unittest
from presence import MacPresence, interpret

class PresenceTests(unittest.TestCase):
    def test_missing_and_locked_session(self):
        self.assertEqual(interpret(None,None,None),'unknown')
        self.assertEqual(interpret(True,True,True),'away')
        self.assertEqual(interpret(False,True,False),'away')
        self.assertEqual(interpret(True,True,None),'awake')
        self.assertEqual(interpret(True,False,None),'unknown')

    def test_no_startup_greeting_and_short_lived_return_token(self):
        now=[100.];value=['awake'];m=MacPresence(lambda:value[0],lambda:now[0])
        self.assertEqual(m.snapshot(),('awake',0))
        value[0]='away';now[0]=102;self.assertEqual(m.snapshot(),('away',0))
        value[0]='awake';now[0]=110;state,token=m.snapshot()
        self.assertEqual(state,'awake');self.assertGreater(token,0)
        now[0]=115;self.assertEqual(m.snapshot()[1],token)
        now[0]=121;self.assertEqual(m.snapshot()[1],0)
        value[0]='away';now[0]=122;m.snapshot();value[0]='awake';now[0]=126
        self.assertEqual(m.snapshot()[1],0) # Repeated locks do not spam greetings.
        value[0]='away';now[0]=170;m.snapshot();value[0]='awake';now[0]=173
        self.assertNotEqual(m.snapshot()[1],0)

    def test_failure_unknown_and_too_short_transition_do_not_greet(self):
        now=[0.];state=['away'];m=MacPresence(lambda:state[0],lambda:now[0]);m.snapshot()
        now[0]=1;state[0]='awake';self.assertEqual(m.snapshot()[1],0)
        now[0]=3;state[0]='invalid';self.assertEqual(m.snapshot(),('unknown',0))
        now[0]=4;state[0]='awake';self.assertEqual(m.snapshot(),('awake',0))
        def fail():raise OSError()
        m.reader=fail;now[0]=5;self.assertEqual(m.snapshot(),('unknown',0))
