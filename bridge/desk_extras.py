"""本机工作接力与音乐元数据；不保存历史、读取账号或采集音频。"""
import hashlib
import json
import math
from pathlib import Path
import secrets
import subprocess
import threading
import time
from task_actions import valid_thread_id

PLAYERS = {'com.tencent.QQMusicMac': 'QQ 音乐', 'com.netease.163music': '网易云音乐'}


def screen_text(value, limit=32):
    if not isinstance(value, str): return ''
    return ''.join(c for c in value if (0x20 <= ord(c) <= 0x7e or 0xa0 <= ord(c) <= 0x24f or
                0x2010 <= ord(c) <= 0x2027 or 0x3000 <= ord(c) <= 0x303f or
                0x4e00 <= ord(c) <= 0x9fff or 0xff01 <= ord(c) <= 0xff60)).strip()[:limit]


def track_key(data):
    # 使用原始元数据校验操作目标，不能仅以被截短的屏幕标题作为身份。
    value='\n'.join(str(data.get(k) or '') for k in ('bundleIdentifier','title','artist','album','duration'))
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def music_snapshot(data):
    if not isinstance(data, dict) or data.get('bundleIdentifier') not in PLAYERS: return None
    title=screen_text(data.get('title'))
    if not title: return None
    def seconds(key):
        v=data.get(key,0)
        return min(86400,max(0,int(v))) if type(v) in (int,float) and math.isfinite(v) else 0
    playing=data.get('playing') is True
    duration=seconds('duration')
    # media-control --now 对暂停快照也可能外推；暂停必须用原 elapsedTime。
    elapsed=seconds('elapsedTimeNow' if playing else 'elapsedTime')
    if duration: elapsed=min(duration,elapsed)
    return dict(source=data['bundleIdentifier'],player=PLAYERS[data['bundleIdentifier']],
                key=track_key(data),title=title,artist=screen_text(data.get('artist')),
                playing=playing,elapsed=elapsed,duration=duration)


class WorkRecap:
    def __init__(self):
        self.previous=None;self.last_at=None;self.last_tasks={};self.left_at=None
        self.baseline={};self.partial=False;self.token=0;self.until=0;self.done={}
        self.rows=[]

    def dismiss(self):
        self.token=0;self.rows=[];self.done={}

    def observe(self, tasks, presence, valid, now):
        current={t['id']:t for t in tasks[:8] if valid_thread_id(t.get('id'))} if valid else {}
        gap=self.last_at is not None and (now-self.last_at>12 or now<self.last_at)
        if presence=='away' and self.previous=='awake':
            self.left_at=now;self.baseline={k:t.get('done_key','') for k,t in self.last_tasks.items()}
            self.partial=not valid;self.dismiss()
        # 睡眠可能跳过锁屏采样；只对比睡前/恢复后的状态，不猜中间过程。
        if gap and presence=='awake' and self.previous=='awake' and self.left_at is None:
            self.left_at=self.last_at;self.baseline={k:t.get('done_key','') for k,t in self.last_tasks.items()};self.partial=True
        if self.left_at is not None and (gap or not valid or presence=='unknown'):self.partial=True
        if valid and presence=='awake' and self.left_at is not None:
            if now-self.left_at>=30:
                self.done={k:t.get('done_key') for k,t in current.items()
                           if t.get('state')=='done' and t.get('done_key') and
                           t.get('done_key')!=self.baseline.get(k) and
                           type(t.get('completed_at')) in (int,float) and self.left_at<=t['completed_at']<=now}
                self.token=secrets.randbelow(4294967295)+1;self.until=now+900
            self.left_at=None
        if self.token:
            if now>=self.until:self.dismiss()
            else:
                waiting=[dict(id=k,title=screen_text(t.get('title')) or '未命名任务',kind='wait') for k,t in current.items() if t.get('state')=='needs_input']
                completed=[dict(id=k,title=screen_text(t.get('title')) or '未命名任务',kind='done') for k,t in current.items()
                           if t.get('state')=='done' and self.done.get(k)==t.get('done_key')]
                self.rows=(waiting+completed)[:8] if valid and presence=='awake' else []
        self.previous=presence;self.last_at=now
        if valid:self.last_tasks=current

    def snapshot(self):
        return dict(token=self.token,partial=self.partial,rows=self.rows,
                    waiting=sum(r['kind']=='wait' for r in self.rows),completed=sum(r['kind']=='done' for r in self.rows))


class MusicReader:
    def __init__(self):
        self.lock=threading.Lock();self.enabled=False;self.value=None;self.at=0;self.error='off'
        self.started=False
        self.binary=next((str(p) for p in (Path('/opt/homebrew/bin/media-control'),Path('/usr/local/bin/media-control')) if p.is_file()),None)

    def set_enabled(self, enabled):
        with self.lock:
            self.enabled=enabled
            if not enabled:self.value=None;self.error='off'
        if enabled and not self.started:
            self.started=True;threading.Thread(target=self.loop,daemon=True,name='music-metadata').start()

    def loop(self):
        while True:
            with self.lock: enabled=self.enabled
            if enabled:
                try:
                    if not self.binary:raise FileNotFoundError()
                    result=subprocess.run([self.binary,'get','--now','--no-artwork'],capture_output=True,timeout=3,check=True)
                    if len(result.stdout)>32768:raise ValueError()
                    value=music_snapshot(json.loads(result.stdout));error='' if value else 'no_player'
                except FileNotFoundError:value=None;error='missing_helper'
                except (OSError,ValueError,subprocess.SubprocessError):value=None;error='unavailable'
                with self.lock:
                    if self.enabled:self.value=value;self.at=time.monotonic();self.error=error
            time.sleep(2)

    def snapshot(self):
        with self.lock:
            if not self.enabled:return None,'off'
            if time.monotonic()-self.at>6:return None,'unavailable'
            return dict(self.value) if self.value else None,self.error


class DeskExtras:
    def __init__(self, runtime):
        self.runtime=Path(runtime);self.recap=WorkRecap();self.music=MusicReader()
        self.enabled={'recap':True,'music':False}
        try:
            data=json.loads((self.runtime.parent/'desk-settings.json').read_text())
            for k in self.enabled:
                if type(data.get(k)) is bool:self.enabled[k]=data[k]
        except (OSError,ValueError):pass
        self.current_presence='unknown';self.data_ok=False;self.supported=None;self.last_sync=0;self.last_action=0;self.armed=False
        self.last_result='';self.latest_music=None

    def configure(self,key,value):
        from runtime import atomic_json
        next_settings=dict(self.enabled);next_settings[key]=value
        atomic_json(self.runtime.parent/'desk-settings.json',next_settings);self.enabled=next_settings
        if not self.enabled['recap']:self.recap=WorkRecap()

    def observe(self,tasks,presence,valid,now):
        self.current_presence=presence;self.data_ok=valid
        if self.enabled['recap']:self.recap.observe(tasks,presence,valid,now)
        self.music.set_enabled(self.enabled['music'] and presence=='awake')
        self.latest_music,error=self.music.snapshot()
        self.music_error=error

    def snapshot(self):
        return dict(settings=self.enabled,recap=self.recap.snapshot(),music=self.latest_music,
                    music_error=getattr(self,'music_error','off'),supported=self.supported,last_result=self.last_result)

    def reset_link(self):self.supported=None;self.armed=False;self.last_sync=0;self.last_action=0

    def action(self,kind,target,token,source):
        if self.current_presence!='awake':return 'locked'
        if kind=='dismiss':
            if str(self.recap.token)!=token:return 'stale'
            self.recap.dismiss();return 'ok'
        if kind=='open':
            if not self.data_ok or str(self.recap.token)!=token:return 'stale'
            rows=self.recap.rows
            try:tasks=source.snapshot()
            except Exception:return 'failed'
            row=next((r for r in rows if r['id']==target),None)
            task=next((t for t in tasks[:8] if t['id']==target),None)
            if not row or not task:return 'stale'
            if row['kind']=='wait' and task['state']!='needs_input':return 'stale'
            if row['kind']=='done' and (task['state']!='done' or task.get('done_key')!=self.recap.done.get(target)):return 'stale'
            subprocess.run(['/usr/bin/open',f'codex://threads/{target}?hostId=local'],check=True,timeout=2,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            return 'opened'
        if kind not in ('toggle','next','previous') or not self.enabled['music']:return 'stale'
        music,error=self.music.snapshot()
        if not music or music['key']!=target:return 'stale'
        # 原生助手再次核对播放器、歌曲与当前 AirPods 输出；不改音量或声音路由。
        binary=self.runtime.parent/'微光控制台.app/Contents/MacOS/WeiguangPanel'
        result=subprocess.run([str(binary),'--music-control',kind,music['source'],target],capture_output=True,timeout=3.5)
        try:reply=json.loads(result.stdout)
        except ValueError:return 'failed'
        return reply.get('result','failed') if reply.get('result') in ('sent','headphones','stale','failed') else 'failed'

    def maintain(self,bridge,stop=None):
        if not bridge.control or not bridge.link or bridge.baseline_pending or time.monotonic()-self.last_sync<1.5:return
        self.last_sync=time.monotonic()
        def exchange(fields,prefix):
            bridge.seq+=1;seq=str(bridge.seq);bridge.link.write(('\t'.join([fields[0],seq]+fields[1:])+'\n').encode())
            deadline=time.monotonic()+1.5
            while time.monotonic()<deadline and not (stop and stop.is_set()):
                raw=bridge.link.readline().strip()
                if raw==b'ERROR\tcommand':return None
                if raw.startswith((prefix+'\t'+seq+'\t').encode()):return raw.decode().split('\t')[2:]
            return None
        if self.supported is None:
            self.supported=exchange(['DESK_INFO'],'DESK_CAP')==['1']
        if not self.supported:return
        recap=self.recap.snapshot();rows=recap['rows'] if self.current_presence=='awake' and self.data_ok else []
        fields=['RECAP_SET',str(recap['token']),str(int(recap['partial'])),str(len(rows))]
        for row in rows:fields += [row['id'],row['kind'],row['title'].encode().hex()]
        if exchange(fields,'DESK_OK')!=['ok']:self.supported=None;return
        m=self.latest_music if self.current_presence=='awake' else None
        fields=['MUSIC_SET','1' if m else '0']
        if m:fields += [m['source'],m['key'],str(int(m['playing'])),str(m['elapsed']),str(m['duration']),m['title'].encode().hex(),m['artist'].encode().hex() or '-']
        if exchange(fields,'DESK_OK')!=['ok']:self.supported=None;return
        event=exchange(['DESK_POLL','poll' if self.armed else 'arm'],'DESK_EVENT')
        if not event or len(event)!=4:self.armed=False;return
        was_armed=self.armed;self.armed=True
        serial,kind,target,token=event
        if not serial.isdigit() or not was_armed or int(serial)<=self.last_action:return
        self.last_action=int(serial)
        try:self.last_result=self.action(kind,target,token,bridge.source)
        except (OSError,ValueError,subprocess.SubprocessError):self.last_result='failed'
        exchange(['DESK_RESULT',serial,self.last_result],'DESK_OK')
