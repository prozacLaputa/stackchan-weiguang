import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from desk_extras import WorkRecap, music_snapshot, track_key, DeskExtras
from control import validate_request

ID='00000000-0000-4000-8000-000000000001'
ID2='00000000-0000-4000-8000-000000000002'
def task(state='running',key='',at=None,id=ID):
    return dict(id=id,title='测试任务',state=state,done_key=key,completed_at=at)

class RecapTests(unittest.TestCase):
    def test_no_startup_or_short_absence_replay(self):
        r=WorkRecap();r.observe([task('done','old',1)],'awake',True,100)
        self.assertFalse(r.token)
        r.observe([task()],'away',True,101);r.observe([task('done','new',105)],'awake',True,110)
        self.assertFalse(r.token)

    def test_return_and_current_state_filter(self):
        r=WorkRecap();r.observe([task()],'awake',True,100);r.observe([task()],'away',True,101)
        r.observe([task('done','new',130),task('needs_input',id=ID2)],'awake',True,145)
        self.assertEqual((r.snapshot()['completed'],r.snapshot()['waiting']),(1,1))
        r.observe([task(),task('done','another',148,id=ID2)],'awake',True,149)
        self.assertEqual(r.rows,[]) # 后续新完成不冒充离席期间结果；重新运行立即移除。

    def test_sleep_gap_is_partial_and_no_old_completion(self):
        r=WorkRecap();r.observe([task('done','old',1)],'awake',True,100)
        r.observe([task('done','old',1),task('needs_input',id=ID2)],'awake',True,180)
        self.assertTrue(r.partial);self.assertEqual(r.snapshot()['completed'],0)
        self.assertEqual(r.snapshot()['waiting'],1)
        r.dismiss();r.observe([task('needs_input',id=ID2)],'awake',True,181)
        self.assertFalse(r.token)

    def test_unknown_and_expiry_hide_old_data(self):
        r=WorkRecap();r.observe([task()],'awake',True,1);r.observe([task()],'away',True,2)
        r.observe([task('done','a',20)],'awake',True,50)
        r.observe([],'unknown',False,51);self.assertEqual(r.rows,[])
        r.observe([task('done','a',20)],'awake',True,951);self.assertFalse(r.token)

class MusicTests(unittest.TestCase):
    def test_qq_paused_does_not_extrapolate_and_bounds_text(self):
        raw=dict(bundleIdentifier='com.tencent.QQMusicMac',title='歌名\n😀',artist='作者',playing=False,elapsedTime=12,elapsedTimeNow=999,duration=100)
        m=music_snapshot(raw);self.assertEqual(m['elapsed'],12);self.assertEqual(m['title'],'歌名')
        raw['playing']=True;self.assertEqual(music_snapshot(raw)['elapsed'],100)

    def test_netease_and_other_source_and_nonfinite(self):
        raw=dict(bundleIdentifier='com.netease.163music',title='Song',playing=True,elapsedTimeNow=float('nan'),duration=float('inf'))
        self.assertEqual(music_snapshot(raw)['elapsed'],0)
        raw['bundleIdentifier']='com.apple.Safari';self.assertIsNone(music_snapshot(raw))
        raw['bundleIdentifier']='com.tencent.QQMusicMac';raw['title']='\n';self.assertIsNone(music_snapshot(raw))

    def test_track_identity_changes_even_when_titles_truncate(self):
        a=dict(bundleIdentifier='com.tencent.QQMusicMac',title='a'*40,artist='x',duration=100)
        b=dict(a,title='a'*41)
        self.assertNotEqual(track_key(a),track_key(b))

    def test_settings_and_stale_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            e=DeskExtras(Path(tmp)/'runtime');e.configure('music',True)
            self.assertTrue(DeskExtras(Path(tmp)/'runtime').enabled['music'])
            self.assertEqual(e.action('toggle','wrong','0',None),'locked')
            e.current_presence='awake';self.assertEqual(e.action('toggle','wrong','0',None),'stale')
            self.assertEqual(e.action('open',ID,'123',None),'stale')

    def test_control_validation(self):
        validate_request(dict(action='desk',operation='configure',key='music',enabled=True))
        with self.assertRaises(ValueError):validate_request(dict(action='desk',operation='configure',key='music',enabled=1))
        with self.assertRaises(ValueError):validate_request(dict(action='desk',operation='shell',target='open',token=0))

    def test_recap_open_rechecks_current_state_before_opening(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            e=DeskExtras(Path(tmp)/'runtime');e.current_presence='awake';e.data_ok=True
            e.recap.token=42;e.recap.rows=[dict(id=ID,title='任务',kind='done')];e.recap.done={ID:'new'}
            with patch('desk_extras.subprocess.run') as run:
                self.assertEqual(e.action('open',ID,'42',SimpleNamespace(snapshot=lambda:[task()])), 'stale')
                run.assert_not_called()
                self.assertEqual(e.action('open',ID,'42',SimpleNamespace(snapshot=lambda:[task('done','new',1)])), 'opened')
                self.assertEqual(run.call_args[0][0],['/usr/bin/open',f'codex://threads/{ID}?hostId=local'])

    def test_wire_negotiation_arm_and_no_action_replay(self):
        from types import SimpleNamespace
        class Link:
            def write(self,raw):
                f=raw.decode().strip().split('\t');seq=f[1]
                if f[0]=='DESK_INFO':self.reply=f'DESK_CAP\t{seq}\t1'
                elif f[0]=='DESK_POLL':self.reply=f'DESK_EVENT\t{seq}\t7\tdismiss\t-\t42'
                else:self.reply=f'DESK_OK\t{seq}\tok'
            def readline(self):return self.reply.encode()
        with tempfile.TemporaryDirectory() as tmp:
            e=DeskExtras(Path(tmp)/'runtime');e.current_presence='awake';e.data_ok=True;e.recap.token=42
            b=SimpleNamespace(control=True,link=Link(),baseline_pending=False,seq=1,source=None)
            with patch.object(e,'action',return_value='ok') as action:
                e.maintain(b);action.assert_not_called() # arm 消费旧意图。
                e.last_sync=0;e.maintain(b);action.assert_called_once()
                e.last_sync=0;e.maintain(b);action.assert_called_once()

if __name__=='__main__':unittest.main()
