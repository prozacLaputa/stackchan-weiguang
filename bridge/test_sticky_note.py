import json
import unittest
from control import Command,parse_note,valid_note_text,validate_request
from diagnostics import clean_snapshot
import test_companion

class NoteTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_companion.CompanionTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.bridge=self.fixture.bridge;self.link=self.fixture.link;self.bridge.device={'firmware':'0.46'}
        self.rev=0;self.state='empty';self.body=''
        def read():
            fields=self.link.fields
            if fields[0]=='NOTE_SET':
                if int(fields[2])!=self.rev:return f'NOTE_ERROR\t{fields[1]}\tconflict'.encode()
                self.rev+=1;self.state='done' if fields[3]=='done' else 'active'
                if fields[3]=='set':self.body=bytes.fromhex(fields[4]).decode()
            return f'NOTE\t{fields[1]}\t{self.rev}\t{self.state}\t{self.body.encode().hex() or "-"}\t0'.encode()
        self.link.readline=read

    def send(self,operation,revision=0,text=None):
        request=dict(action='note',operation=operation,expected_revision=revision)
        if text is not None:request['text']=text
        command=Command(request);self.fixture.hub.queue.put(command);self.bridge.maintain_device();return command.result

    def test_set_done_restore_and_source_of_truth(self):
        answer=self.send('set',text='下班带充电器');self.assertTrue(answer['ok']);self.assertEqual(answer['note']['text'],'下班带充电器')
        self.assertTrue(self.send('done',1)['ok']);self.assertEqual(self.bridge.note['state'],'done')
        self.assertTrue(self.send('restore',2)['ok']);self.assertEqual(self.bridge.note['state'],'active')
        self.assertEqual(self.send('set',1,'旧请求')['error'],'conflict');self.assertEqual(self.bridge.note['text'],'下班带充电器')
        self.bridge.last_note_query=0;self.bridge.maintain_note();self.assertIsNone(self.bridge.note_error)
        self.assertEqual(json.loads((self.fixture.root/'status.json').read_text())['note']['revision'],3)

    def test_text_limits_and_bad_payloads(self):
        self.assertTrue(valid_note_text('中'*32));self.assertTrue(valid_note_text('今晚 7 点，记得带伞！'))
        for text in ('',' '*4,'🐱','a\nb','\x00','中'*33,'a\u202eb','a\u2028b','\ud800'):
            self.assertFalse(valid_note_text(text))
            with self.assertRaises(ValueError):validate_request(dict(action='note',operation='set',text=text,expected_revision=0))
        for rev in (-1,4294967296,True,'0'):
            with self.assertRaises(ValueError):validate_request(dict(action='note',operation='done',expected_revision=rev))
        for raw in (b'NOTE\t1\t0\tactive\t61\t0',b'NOTE\t1\t0\tempty\t61\t0',b'NOTE\t1\t1\tactive\tzz\t0',b'NOTE\t1\t1\tactive\ted a0 80\t0',b'NOTE\t1\t1\tactive\t61\t2'):
            with self.assertRaises(ValueError):parse_note(raw,1)

    def test_disconnected_expired_and_old_firmware_never_replay(self):
        command=Command(dict(action='note',operation='set',text='不要补发',expected_revision=0));command.expires-=10
        self.bridge.maintain_note(command=command);self.assertEqual(command.result['error'],'confirmation_timeout');self.assertFalse(self.link.packets)
        self.bridge.device={'firmware':'0.45'}
        self.assertEqual(self.send('set',text='旧固件')['error'],'firmware_update_required');self.assertFalse(self.link.packets)
        self.bridge.disconnect();self.assertEqual(self.send('set',text='断连')['error'],'device_unavailable');self.assertTrue(self.fixture.hub.queue.empty())

    def test_failures_and_diagnostic_privacy(self):
        self.send('set',text='私人便签内容')
        snapshot=json.loads((self.fixture.root/'status.json').read_text())
        self.assertNotIn('私人便签内容',json.dumps(clean_snapshot(snapshot),ensure_ascii=False))
        self.link.readline=lambda:f'NOTE_ERROR\t{self.link.fields[1]}\tsave_failed'.encode()
        self.assertEqual(self.send('done',1)['error'],'save_failed');self.assertEqual(self.bridge.note['state'],'active')
        self.link.readline=lambda:f'NOTE\t{self.link.fields[1]}\t1\tactive\tzz\t0'.encode()
        self.bridge.maintain_note();self.assertIsNone(self.bridge.link)
