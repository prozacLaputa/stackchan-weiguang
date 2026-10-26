"""最小异常留档与本机诊断导出；字段白名单，不复制原始日志或聊天数据。"""
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import stat
import tempfile
import time
import zipfile

VERSION = '0.49'
LIMIT = 128 * 1024
PARTS = 3
CONNECTIONS = {'connected','waiting_ble','waiting_usb','waiting_ack','stopped'}
MOTION = {'ready','moving','cooldown','disabled','unavailable','screen','release','sensor','checking'}
REASONS = {'none','not-initialized','bus-init','power-init','torque-release','calibration',
           'position-read','position-range','load-high','release-ack','torque-read','command-ack',
           'pet-command-ack','feedback-range','pet-follow-error','timeout','not-reached','return-ack',
           'no-event','disabled','busy','preference','cooldown','already-moving','position-limit',
           'settling','screen-touch','release-required','head-read','too-short'}
ERRORS = {'confirmation_timeout','firmware_update_required','invalid','invalid_device_reply','save_failed',
          'device_unavailable','disconnected','OSError','SerialException','RuntimeError','OperationalError',
          'DatabaseError','ValueError','ble_helper_protocol','ble_helper_stopped','ble_helper_overflow',
          'ble_binding_missing','ble_connect_timeout','ble_not_open','ble_reply_invalid','ble_error',
          'bluetooth_unavailable','bluetooth_unauthorized','device_not_found','authentication_failed'}
KINDS = {'service_started','service_stopped','service_error','link_waiting','link_recovered','link_connected',
         'data_unavailable','data_recovered','device_issue','device_recovered','motion_issue','motion_recovered',
         'pet_issue','pet_recovered'}
RESULTS = {'none','detected','moving','completed','skipped','stopped','failed'}


def code(value, choices):
    return value if isinstance(value,str) and value in choices else 'unknown'


def number(value, low=0, high=4294967295):
    return value if type(value) in (float,int) and math.isfinite(value) and low<=value<=high else None


def clean_device(value):
    value=value if isinstance(value,dict) else {};out={}
    for key,high in {'battery':100,'charging':1,'resting':1,'brightness':255,'light':3,'rest':4,'pet':1,
                     'save_error':1,'uptime':4294967,'sync_age':4294967,'wait_motion':1,'done_motion':1,
                     'pet_cooldown_ms':5000,'head_sensor':1,'pet_event':4294967295,'pet_age':4294967,'head_down':1,'skin':1,'focus_motion':1,'motion_fault_id':4294967295,'motion_fault_at':4294967295,'motion_fault_phase':2,
                     'motion_fault_command_age':4294967295,'motion_fault_sample_gap':4294967295,'motion_recoverable':1}.items():
        n=value.get(key)
        if type(n) is int and (-1 if key=='battery' else 0)<=n<=high:out[key]=n
    for key,low,high in (('motion_fault_position',-32768,65535),('motion_fault_command',-1,1000),('motion_fault_load',-32768,32767)):
        n=value.get(key)
        if type(n) is int and low<=n<=high:out[key]=n
    version=value.get('firmware')
    if isinstance(version,str) and re.fullmatch(r'\d{1,3}\.\d{1,3}(?:\.\d{1,3})?',version):out['firmware']=version
    for key,choices in {'page':{'home','list','settings','game','focus'},'motion_state':MOTION,'motion_reason':REASONS,
                        'pet_result':RESULTS,'pet_reason':REASONS,'motion_fault_reason':REASONS}.items():
        if key in value:out[key]=code(value[key],choices)
    return out


def clean_snapshot(value, now=None):
    value=value if isinstance(value,dict) else {};now=time.time() if now is None else now
    out={'connection':code(value.get('connection'),CONNECTIONS),
         'transport':code(value.get('transport'),{'ble','usb'}),
         'data_source':code(value.get('data_source'),{'ok','unavailable'}),
         'error':code(value.get('error'),ERRORS) if value.get('error') else None,
         'device_error':code(value.get('device_error'),ERRORS) if value.get('device_error') else None,
         'device':clean_device(value.get('device'))}
    for key,high in {'tasks':8,'running':8,'needs_input':8,'ack_ms':60000}.items():
        n=number(value.get(key),high=high)
        if n is not None:out[key]=n
    stamp=number(value.get('device_at'),high=1e12)
    age=now-stamp if stamp is not None else None
    out['device_age_seconds']=round(age,2) if age is not None and 0<=age<=1e9 else None
    out['device_live']=out['connection']=='connected' and not out['device_error'] and age is not None and 0<=age<25
    return out


def read_bounded(path, limit):
    # 不跟随人为替换的符号链接，不读取任意文件/管道。
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        meta=os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_size>limit:raise ValueError('invalid_diagnostic_file')
        return stream.read(limit+1)


@contextlib.contextmanager
def journal_lock(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(directory/'diagnostics.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        yield


def event_record(kind,snapshot,at):
    return {'schema':1,'at':at,'kind':kind,'snapshot':snapshot}


class Journal:
    def __init__(self,directory,limit=LIMIT):
        self.directory=Path(directory);self.limit=limit;self.last={};self.started=False

    def _append(self,record):
        encoded=(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n').encode()
        if len(encoded)>self.limit:raise ValueError('diagnostic_event_too_large')
        path=self.directory/'diagnostics.jsonl'
        if path.exists() and path.stat().st_size+len(encoded)>self.limit:
            for i in range(PARTS-1,0,-1):
                older=path if i==1 else path.with_name(path.name+f'.{i-1}')
                if older.exists():older.replace(path.with_name(path.name+f'.{i}'))
        fd=os.open(path,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'ab') as stream:
            os.fchmod(stream.fileno(),0o600);stream.write(encoded)

    def capture_motion_fault(self,device):
        safe=clean_device(device)
        if not safe.get('motion_fault_id') or safe.get('motion_fault_reason') not in REASONS-{'none'}:return False
        record={k:v for k,v in safe.items() if k.startswith('motion_fault_') or k in ('firmware','uptime')}
        with journal_lock(self.directory):
            path=self.directory/'motion-last-fault.json'
            try:
                old=json.loads(read_bounded(path,4096))
                if isinstance(old,dict) and isinstance(old.get('device'),dict) and old['device'].get('motion_fault_id')==record['motion_fault_id']:return True
            except (OSError,ValueError):pass
            temp=self.directory/'motion-last-fault.json.tmp'
            fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as stream:
                json.dump({'schema':1,'at':time.time(),'device':record},stream);stream.flush();os.fsync(stream.fileno())
            temp.replace(path)
        return True

    def observe(self,value):
        now=time.time();safe=clean_snapshot(value,now)
        if safe['device_live'] and safe['device'].get('motion_fault_id'):self.capture_motion_fault(safe['device'])
        changes=[];next_state=dict(self.last)
        with journal_lock(self.directory):
            if not self.started:
                try:
                    previous=json.loads(read_bounded(self.directory/'diagnostic-state.json',4096))
                    # 持久状态仅用于去重，原文不会进入记录/导出。
                    if isinstance(previous,dict):self.last={k:v for k,v in previous.items() if k in {'connection','data','device','motion','pet'} and isinstance(v,str) and len(v)<64}
                except (OSError,ValueError):pass
                next_state=dict(self.last);changes.append('service_started')
            def transition(key,value,issue,recovered,healthy):
                previous=self.last.get(key)
                if previous!=value:
                    next_state[key]=value
                    if value!=healthy:changes.append(issue)
                    elif previous is not None and previous!=healthy:changes.append(recovered)
            conn=safe['connection']
            if self.last.get('connection')!=conn:
                next_state['connection']=conn
                changes.append('service_stopped' if conn=='stopped' else
                               'link_recovered' if conn=='connected' and self.last.get('connection') in CONNECTIONS-{'connected','stopped'} else
                               'link_connected' if conn=='connected' else 'link_waiting')
            transition('data',safe['data_source'],'data_unavailable','data_recovered','ok')
            transition('device',safe['device_error'] or 'ok','device_issue','device_recovered','ok')
            if safe['device_live'] and safe['device'].get('motion_state') in MOTION:
                d=safe['device'];motion=d.get('motion_state')
                condition=('unavailable:'+d.get('motion_reason','unknown')) if motion in ('unavailable','checking') else 'sensor:head-read' if motion=='sensor' else 'ok'
                transition('motion',condition,'motion_issue','motion_recovered','ok')
                # 正常冷却、触屏、开关操作不留为异常；已记录的异常只在正常点头后确认恢复。
                cleared_old_fault=bool(d.get('motion_fault_id') and d.get('motion_reason')=='none' and d.get('pet_result')=='failed' and d.get('pet_reason')==d.get('motion_fault_reason'))
                if motion not in ('unavailable','checking') and not cleared_old_fault and d.get('pet_result') in {'failed','stopped','skipped'} and d.get('pet_reason') in REASONS-{'none','settling','screen-touch','preference','disabled','cooldown','busy','release-required','too-short'}:
                    transition('pet',d['pet_reason'],'pet_issue','pet_recovered','ok')
                elif d.get('pet_result')=='completed':transition('pet','ok','pet_issue','pet_recovered','ok')
            for kind in changes:self._append(event_record(kind,safe,now))
            if changes:
                temp=self.directory/'diagnostic-state.json.tmp'
                fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
                with os.fdopen(fd,'w') as stream:json.dump(next_state,stream)
                temp.replace(self.directory/'diagnostic-state.json')
            self.last=next_state;self.started=True

    def service_error(self,value):
        with journal_lock(self.directory):self._append(event_record('service_error',clean_snapshot(value),time.time()))


def read_events(directory):
    events=[];ignored=0
    with journal_lock(directory):
        for suffix in ('.2','.1',''):
            try:data=read_bounded(Path(directory)/('diagnostics.jsonl'+suffix),LIMIT)
            except FileNotFoundError:continue
            except (OSError,ValueError):ignored+=1;continue
            for line in data.splitlines():
                try:
                    record=json.loads(line)
                    if not isinstance(record,dict) or record.get('kind') not in KINDS:raise ValueError()
                    at=number(record.get('at'),high=1e12)
                    if at is None:raise ValueError()
                    # 再做字段白名单，拒绝旧日志或人工插入的自由文本。
                    raw=record.get('snapshot');raw=raw if isinstance(raw,dict) else {}
                    safe=clean_snapshot(raw,at)
                    age=number(raw.get('device_age_seconds'),high=1e9)
                    safe['device_age_seconds']=age
                    safe['device_live']=raw.get('device_live') is True and age is not None and age<25 and safe['connection']=='connected' and not safe['device_error']
                    events.append(event_record(record['kind'],safe,at))
                except (ValueError,TypeError):ignored+=1
    return events,ignored


def export_bundle(loc,state):
    now=time.time();state=state if isinstance(state,dict) else {}
    try:raw=json.loads(read_bounded(loc.runtime/'status.json',256*1024))
    except (OSError,ValueError):raw={}
    snapshot=clean_snapshot(raw,now)
    fresh=state.get('fresh') is True and state.get('paused') is not True
    snapshot['device_live']=snapshot['device_live'] and fresh
    report={'schema':1,'created_at':now,'bridge_version':VERSION,
            'macos_version':platform.mac_ver()[0],'python_version':platform.python_version(),
            'service':{k:state.get(k) is True for k in ('installed','loaded','paused','fresh')},
            'last_snapshot':snapshot,'journal_ok':raw.get('diagnostics_ok') if type(raw.get('diagnostics_ok')) is bool else None}
    events,ignored=read_events(loc.runtime);report.update(event_count=len(events),ignored_records=ignored)
    entries={'report.json':json.dumps(report,ensure_ascii=False,indent=2).encode(),
             'events.jsonl':('\n'.join(json.dumps(row,ensure_ascii=False) for row in events)+'\n').encode(),
             '说明.txt':('微光本机诊断包 v'+VERSION+'\n\n仅包含版本、设备/连接状态、任务计数及有限的异常与恢复记录。\n'
                         '不包含任务标题、会话 ID、聊天正文、密钥、设备绑定、账户资料、用户名/本机路径、原始日志或原厂备份。\n'
                         '不会自动上传，也不发机器人控制命令。\n\n'
                         'at 和 created_at 为 Unix 时间（秒）。device_live=false 表示上次记录，不能当作当前设备状态。\n'
                         '从安装本版起留档；只记录 Mac 实际收到的异常。服务停止、Mac 睡眠、蓝牙断开期间无法完整观察机器人。\n'
                         '记录最多保留约 384 KiB，正常冷却和日常触摸不逐条记录；轮换或异常文件可能导致历史不完整。\n').encode()}
    try:
        last=json.loads(read_bounded(loc.runtime/'motion-last-fault.json',4096))
        last_device=clean_device(last.get('device'));at=number(last.get('at'),high=1e12)
        if last_device.get('motion_fault_id') and at is not None:
            entries['last-motion-fault.json']=json.dumps({'schema':1,'at':at,'device':last_device},ensure_ascii=False).encode()
    except (OSError,ValueError,TypeError):pass
    entries['SHA256SUMS.json']=json.dumps({name:hashlib.sha256(data).hexdigest() for name,data in entries.items()},indent=2).encode()
    destination=loc.root/'diagnostics';destination.mkdir(mode=0o700,exist_ok=True)
    if destination.is_symlink():raise ValueError('invalid_diagnostic_directory')
    stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    fd,name=tempfile.mkstemp(prefix=f'微光-诊断-{stamp}-',suffix='.zip',dir=destination)
    try:
        with os.fdopen(fd,'w+b') as stream:
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
                for key,data in entries.items():archive.writestr(key,data)
        return {'ok':True,'path':name,'events':len(events)}
    except BaseException:
        Path(name).unlink(missing_ok=True);raise
