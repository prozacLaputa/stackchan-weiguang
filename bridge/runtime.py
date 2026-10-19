"""微光后台同步：设备发现、单实例、状态与断线恢复。"""
import contextlib
import datetime as dt
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import threading
import time

VID, PID = 0x303A, 0x1001


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600)
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    temporary.replace(path)


@contextlib.contextmanager
def single_instance(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / 'bridge.lock').open('a+') as lock:
        os.chmod(lock.name, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('已有微光同步进程运行，请使用暂停／恢复入口。') from None
        lock.seek(0)
        lock.truncate()
        lock.write(str(os.getpid()))
        lock.flush()
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def select_port(ports, serial_number=None):
    candidates = [p for p in ports if p.vid == VID and p.pid == PID
                  and p.device.startswith('/dev/cu.')
                  and (not serial_number or p.serial_number == serial_number)]
    if len(candidates) > 1:
        raise RuntimeError('检测到多个候选设备，请安装时指定 --serial-number。')
    return candidates[0].device if candidates else None


def find_database(codex_home):
    candidates = []
    for path in Path(codex_home).glob('state_*.sqlite'):
        match = re.fullmatch(r'state_(\d+)\.sqlite', path.name)
        if match:
            candidates.append((int(match[1]), path))
    if not candidates:
        raise FileNotFoundError('等待本机 Codex 创建会话数据库')
    # 不能在新版结构不兼容时回退旧库，避免展示过期状态。
    return max(candidates)[1]


class NotificationGate:
    """连接恢复时已有事件不补播，之后的新事件照常传递。"""
    def __init__(self):
        self.baseline = None

    def reset(self):
        self.baseline = None

    def filter(self, tasks):
        if self.baseline is None:
            self.baseline = {t['id']: (t.get('done_key', ''), t.get('wait_key', ''),
                                      t.get('completed_at', 0)) for t in tasks}
        output = []
        for task in tasks:
            copy = dict(task)
            previous = self.baseline.get(task['id'])
            if previous:
                for field, value in zip(('done_key', 'wait_key'), previous):
                    if copy.get(field, '') == value:
                        copy[field] = ''
                # 首次连接时完成事件可能仍在短暂确认期，之后也不补播。
                if previous[2] and copy.get('completed_at') == previous[2]:
                    copy['done_key'] = ''
            output.append(copy)
        return output


class TaskSource:
    def __init__(self, codex_home, db=None, thread=None):
        self.codex_home, self.db, self.thread = Path(codex_home), db, thread
        self.tails, self.active_db = {}, None
        self.rows,self.rows_at=[],0

    def snapshot(self):
        from monitor import Tail, choose_tasks, recent_tasks
        db = self.db or find_database(self.codex_home)
        if db != self.active_db:
            self.tails.clear()
            self.active_db = db
            self.rows_at=0
        # 名称和候选列表最多每秒查询一次；已有会话的增量事件每轮检查。
        if not self.rows_at or time.monotonic()-self.rows_at>=1:
            self.rows=recent_tasks(db,self.thread)
            self.rows_at=time.monotonic()
        rows=self.rows
        tasks = []
        for tid, path, title, updated in rows:
            if tid not in self.tails or self.tails[tid].path != Path(path):
                self.tails[tid] = Tail(path)
            try:
                state = self.tails[tid].poll()
            except OSError:
                state = 'unknown'
            tracker = self.tails[tid].tracker
            done, wait = tracker.notification_keys() if state != 'unknown' else ('', '')
            tasks.append(dict(id=tid, title=title or '未命名任务', state=state, updated=updated,
                              done_key=done, completed_at=tracker.completed_at, wait_key=wait,
                              wait_reason=tracker.waiting_reason() if state=='needs_input' else '',
                              result_hint=tracker.result_hint if state=='done' else '',
                              progress_hint=tracker.progress.current(time.time(), state),
                              mood=tracker.expression.current(time.time(), state)))
        ids = {r[0] for r in rows}
        self.tails = {key: value for key, value in self.tails.items() if key in ids}
        return choose_tasks(tasks, self.thread)


class Bridge:
    def __init__(self, source, runtime_dir, port='auto', serial_number=None,
                 serial_factory=None, port_provider=None, logger=None, transport="usb",
                 ble_device=None, ble_key_file=None, ble_helper=None, ble_factory=None, control=None, presence=None):
        import serial
        from serial.tools import list_ports
        self.source, self.runtime_dir = source, Path(runtime_dir)
        self.transport=transport
        self.ble_device,self.ble_key_file,self.ble_helper=ble_device,ble_key_file,ble_helper
        self.ble_factory=ble_factory
        self.link_transport=None
        self.last_good_at=None
        self.baseline_pending=True
        self.port, self.serial_number = port, serial_number
        self.serial_factory = serial_factory or serial.Serial
        self.port_provider = port_provider or list_ports.comports
        self.log = logger or logging.getLogger('weiguang')
        self.link = None
        self.tasks = []
        self.gate = NotificationGate()
        self.seq = int(time.time() * 1000) % 1_000_000_000
        self.last_ack = 0
        self.last_cycle = None
        self.previous = None
        self.last_data_ok = False
        self.last_sent_at=0
        self.sent_signature=None
        self.next_connect_at=0
        self.ack_ms=None
        self.control=control
        self.device=None
        self.device_at=None
        self.device_error=None
        self.device_supported=None
        self.last_device_query=0
        self.presence=presence
        from desk_extras import DeskExtras
        self.extras=DeskExtras(self.runtime_dir)
        self.note=None;self.note_at=None;self.note_error=None;self.last_note_query=0
        self.companion=None
        self.companion_at=None
        self.companion_error=None
        self.last_companion_query=0
        self.voice_active=False
        self.voice_acks=0
        self.actions_armed=False
        self.last_action_query=0
        self.last_action_id=0
        from diagnostics import Journal
        self.diagnostics=Journal(self.runtime_dir)

    def disconnect(self):
        self.extras.reset_link()
        self.voice_active=False
        if self.control and hasattr(self.control,'voice'):self.control.voice.clear()
        if self.link is not None:
            try:
                self.link.close()
            except OSError:
                pass
        self.link = None
        self.link_transport=None
        self.baseline_pending=True
        self.gate.reset()
        self.sent_signature=None
        self.device_supported=None
        self.last_device_query=0
        self.last_companion_query=0
        self.companion_error='disconnected'
        self.last_note_query=0;self.note_error='disconnected'
        self.actions_armed=False
        self.last_action_id=0
        self.last_action_query=0
        if self.control:self.device_error='disconnected'

    def status(self, connection, data_ok, error=None):
        value = dict(pid=os.getpid(), updated_at=time.time(), connection=connection,
                     data_source='ok' if data_ok else 'unavailable',
                     port=self.link.port if self.link else None, transport=self.link_transport,
                     last_good_at=self.last_good_at,
                     tasks=len(self.tasks), running=sum(t['state'] == 'running' for t in self.tasks),
                     needs_input=sum(t['state'] == 'needs_input' for t in self.tasks), error=error)
        value.update(ack_ms=self.ack_ms,heartbeat_seconds=5,poll_seconds=.2,voice_face_acks=self.voice_acks)
        from task_actions import pending_tasks, completion_events
        value['pending_tasks'] = pending_tasks(self.tasks) if data_ok else []
        value['completion_events'] = completion_events(self.tasks, value['updated_at']) if data_ok else []
        value['desk_extras']=self.extras.snapshot()
        if self.control:value.update(device=self.device,device_at=self.device_at,device_error=self.device_error,device_supported=self.device_supported)
        if self.control:value.update(note=self.note,note_at=self.note_at,note_error=self.note_error)
        if self.control:value.update(companion=self.companion,companion_at=self.companion_at,companion_error=self.companion_error)
        try:
            self.diagnostics.observe(value);value['diagnostics_ok']=True
        except (OSError,ValueError,TypeError):
            # 留档故障不能打断任务同步；面板明确显示无法留档。
            value['diagnostics_ok']=False
        atomic_json(self.runtime_dir / 'status.json', value)
        state = (connection, data_ok, value['transport'], value['tasks'], value['running'], value['needs_input'], error)
        if state != self.previous:
            self.log.info(json.dumps({k: value[k] for k in ('connection', 'transport', 'data_source', 'tasks', 'running', 'needs_input', 'error')}, ensure_ascii=False))
            self.previous = state

    def maintain_voice(self, stop=None):
        if not self.control or not self.link or self.baseline_pending or not self.device or self.device.get('firmware') not in ('0.47','0.48'):return
        level=self.control.voice.current()
        if level<0 and not self.voice_active:return
        self.seq+=1
        self.link.write(f'VOICE\t{self.seq}\t{level}\n'.encode())
        deadline=time.monotonic()+.3
        while time.monotonic()<deadline and not (stop and stop.is_set()):
            if self.link.readline().strip()==f'VOICE_ACK\t{self.seq}'.encode():
                self.voice_active=level>=0;self.voice_acks+=1;return
        # No retransmission of an old envelope; the next cycle samples latest state.
        # Keep clearing after a lost stop acknowledgement. Firmware independently expires at 600ms.
        self.voice_active=True

    def maintain_device(self, stop=None):
        if self.control is None:return
        from control import parse_device
        command=self.control.take()
        if command and (time.monotonic()>command.expires or command.done.is_set()):
            command.finish({'ok':False,'error':'confirmation_timeout'});return
        if command and command.request['action']=='desk':
            req=command.request
            try:
                if req['operation']=='configure':
                    self.extras.configure(req['key'],req['enabled']);result='ok'
                else:
                    result=self.extras.action(req['operation'],req.get('target','-'),str(req.get('token',0)),self.source)
                command.finish({'ok':result in ('ok','opened','sent'),'result':result})
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):command.finish({'ok':False,'result':'failed'})
            self.status('connected' if self.link else 'waiting_ble',self.last_data_ok);return
        if not self.link or self.baseline_pending:
            if command:command.finish({'ok':False,'error':'device_unavailable'})
            return
        if command and command.request['action']=='motion_recover':
            self.recover_motion(command,stop);return
        if command and command.request['action']=='note':
            self.maintain_note(stop,command);return
        if command and command.request['action']=='focus':
            self.maintain_companion(stop,command);return
        if command is None and (self.device_supported is False or time.monotonic()-self.last_device_query<2):return
        if command and self.device_supported is False:
            command.finish({'ok':False,'error':'firmware_update_required'});return
        self.last_device_query=time.monotonic();self.seq+=1
        fields=['DEVICE_INFO',str(self.seq)]
        if command and command.request['action']=='configure':
            keys=('light','rest','pet')
            supports_motion=self.device and self.device.get('firmware') in ('0.25','0.26','0.28','0.29','0.30','0.32','0.33','0.34','0.35','0.36','0.37','0.38','0.39','0.40','0.41','0.42','0.43','0.44','0.45','0.46','0.47','0.48')
            if supports_motion:keys+=('wait_motion','done_motion')
            elif any(k in command.request['changes'] for k in ('wait_motion','done_motion')):
                command.finish({'ok':False,'error':'firmware_update_required'});return
            if self.device and self.device.get('firmware') in ('0.35','0.36','0.37','0.38','0.39','0.40','0.41','0.42','0.43','0.44','0.45','0.46','0.47','0.48'):keys+=('daily','away_rest','greeting','affection')
            elif any(k in command.request['changes'] for k in ('daily','away_rest','greeting','affection')):
                command.finish({'ok':False,'error':'firmware_update_required'});return
            if self.device and self.device.get('firmware') in ('0.37','0.38','0.39','0.40','0.41','0.42','0.43','0.44','0.45','0.46','0.47','0.48'):keys+=('skin',)
            elif 'skin' in command.request['changes']:
                command.finish({'ok':False,'error':'firmware_update_required'});return
            if self.device and self.device.get('firmware') in ('0.41','0.42','0.43','0.44','0.45','0.46','0.47','0.48'):keys+=('focus_motion',)
            elif 'focus_motion' in command.request['changes']:
                command.finish({'ok':False,'error':'firmware_update_required'});return
            fields=['DEVICE_SET',str(self.seq)]+[str(command.request['changes'].get(key,'-')) for key in keys]
        result={'ok':False,'error':'confirmation_timeout'}
        try:
            self.link.write(('\t'.join(fields)+'\n').encode())
            deadline=time.monotonic()+2.5
            while time.monotonic()<deadline and not (stop and stop.is_set()):
                raw=self.link.readline().strip()
                if raw.startswith(f'DEVICE\t{self.seq}\t'.encode()):
                    self.device=parse_device(raw,self.seq);self.device_at=time.time();self.device_supported=True;self.device_error=None
                    result={'ok':True,'device':self.device,'device_at':self.device_at};break
                if raw==b'ERROR\tcommand':
                    self.device_supported=False;result={'ok':False,'error':'firmware_update_required'};break
                if raw.startswith(f'DEVICE_ERROR\t{self.seq}\t'.encode()):
                    code=raw.split(b'\t')[-1].decode('ascii',errors='replace')
                    result={'ok':False,'error':code if code in ('invalid','save_failed') else 'invalid_device_reply'};break
            if not result['ok']:
                self.device_error=result['error']
                if result['error']=='confirmation_timeout':self.disconnect();self.device_error='confirmation_timeout'
        except (OSError, RuntimeError, ValueError):
            self.disconnect();self.device_error='device_unavailable';result={'ok':False,'error':'device_unavailable'}
        finally:
            if command:command.finish(result)
            self.status('connected' if self.link else 'waiting_ble' if self.transport!='usb' else 'waiting_usb',self.last_data_ok)

    def recover_motion(self,command,stop=None):
        # 单次人工请求，不重连重发；持久保存首个故障后才允许解除锁定。
        expected=command.request['fault_id']
        if not self.device or self.device.get('firmware')!='0.48':
            command.finish({'ok':False,'error':'firmware_update_required'});return
        if not self.device_at or not 0<=time.time()-self.device_at<10 or self.device.get('motion_fault_id')!=expected:
            command.finish({'ok':False,'motion_result':'stale-fault'});return
        try:
            if not self.diagnostics.capture_motion_fault(self.device):raise ValueError('invalid_fault')
        except (OSError,ValueError):
            command.finish({'ok':False,'motion_result':'diagnostic-save-failed'});return
        self.seq+=1;result={'ok':False,'error':'confirmation_timeout'}
        choices={'recovered','already-ready','busy','stale-fault','requires-reset','disabled','head-read','release-required',
                 'cooldown','release-ack','check-timeout','torque-read','position-read','position-range','load-high','not-still','position-limit','connection-lost'}
        try:
            self.link.write(f'MOTION_RECOVER\t{self.seq}\t{expected}\n'.encode())
            deadline=time.monotonic()+2.5
            while time.monotonic()<deadline and not (stop and stop.is_set()):
                raw=self.link.readline().strip()
                if raw.startswith(f'MOTION_RESULT\t{self.seq}\t'.encode()):
                    fields=raw.decode('ascii').split('\t')
                    if len(fields)!=3 or fields[2] not in choices:raise ValueError('invalid_motion_reply')
                    result={'ok':fields[2] in ('recovered','already-ready'),'motion_result':fields[2]};break
                if raw==b'ERROR\tcommand':
                    result={'ok':False,'error':'firmware_update_required'};break
        except (OSError,RuntimeError,ValueError):
            result={'ok':False,'error':'device_unavailable'};self.disconnect()
        self.last_device_query=0
        command.finish(result)
        self.status('connected' if self.link else 'waiting_ble',self.last_data_ok)

    def maintain_note(self,stop=None,command=None):
        from control import parse_note
        if not self.link or self.baseline_pending:
            if command:command.finish({'ok':False,'error':'device_unavailable'})
            return
        if not self.device or self.device.get('firmware') not in ('0.46','0.47','0.48'):
            if command:command.finish({'ok':False,'error':'firmware_update_required'})
            return
        if command is None and time.monotonic()-self.last_note_query<2:return
        if command and (time.monotonic()>command.expires or command.done.is_set()):
            command.finish({'ok':False,'error':'confirmation_timeout'});return
        self.last_note_query=time.monotonic();self.seq+=1
        fields=['NOTE_INFO',str(self.seq)]
        if command and command.request['operation']!='inspect':
            req=command.request
            fields=['NOTE_SET',str(self.seq),str(req['expected_revision']),req['operation'],req.get('text','').encode('utf-8').hex() or '-']
        result={'ok':False,'error':'confirmation_timeout'}
        try:
            self.link.write(('\t'.join(fields)+'\n').encode())
            deadline=time.monotonic()+2.5
            while time.monotonic()<deadline and not (stop and stop.is_set()):
                raw=self.link.readline().strip()
                if raw.startswith(f'NOTE\t{self.seq}\t'.encode()):
                    self.note=parse_note(raw,self.seq);self.note_at=time.time();self.note_error=None
                    result={'ok':True,'note':self.note,'note_at':self.note_at};break
                if raw.startswith(f'NOTE_ERROR\t{self.seq}\t'.encode()):
                    code=raw.split(b'\t')[-1].decode('ascii',errors='replace')
                    result={'ok':False,'error':code if code in ('invalid','conflict','save_failed') else 'invalid_note_reply'};break
                if raw==b'ERROR\tcommand':result={'ok':False,'error':'firmware_update_required'};break
            if not result['ok']:
                self.note_error=result['error'];self.last_note_query=0
                if result['error']=='confirmation_timeout':self.disconnect()
        except (OSError,RuntimeError,ValueError):
            self.disconnect();self.note_error='device_unavailable';result={'ok':False,'error':'device_unavailable'}
        finally:
            if command:command.finish(result)
            self.status('connected' if self.link else 'waiting_ble' if self.transport!='usb' else 'waiting_usb',self.last_data_ok)

    def maintain_companion(self, stop=None, command=None):
        from control import parse_companion
        if not self.link or self.baseline_pending:
            if command:command.finish({'ok':False,'error':'device_unavailable'})
            return
        if not self.device or self.device.get('firmware') not in ('0.34','0.35','0.36','0.37','0.38','0.39','0.40','0.41','0.42','0.43','0.44','0.45','0.46','0.47','0.48'):
            if command:command.finish({'ok':False,'error':'firmware_update_required'})
            return
        if command is None and time.monotonic()-self.last_companion_query<2:return
        if command and (time.monotonic()>command.expires or command.done.is_set()):
            command.finish({'ok':False,'error':'confirmation_timeout'});return
        if command and command.request['operation'] in ('pause','resume') and self.device.get('firmware') not in ('0.40','0.41','0.42','0.43','0.44','0.45','0.46','0.47','0.48'):
            command.finish({'ok':False,'error':'firmware_update_required'});return
        if command and command.request['operation']=='next' and self.device.get('firmware') not in ('0.44','0.45','0.46','0.47','0.48'):
            command.finish({'ok':False,'error':'firmware_update_required'});return
        self.last_companion_query=time.monotonic();self.seq+=1
        if command:
            req=command.request
            fields=['FOCUS_SET',str(self.seq),req['operation'],str(req.get('minutes',0))]
        else:
            state,token=self.presence.snapshot() if self.presence else ('unknown',0)
            fields=['COMPANION_SET',str(self.seq),state,str(token)]
            if self.device.get('firmware') in ('0.45','0.46','0.47','0.48'):
                import calendar
                fields.append(str(calendar.timegm(time.localtime())))
        result={'ok':False,'error':'confirmation_timeout'}
        try:
            self.link.write(('\t'.join(fields)+'\n').encode())
            deadline=time.monotonic()+2.5
            while time.monotonic()<deadline and not (stop and stop.is_set()):
                raw=self.link.readline().strip()
                if raw.startswith(f'COMPANION\t{self.seq}\t'.encode()):
                    self.companion=parse_companion(raw,self.seq);self.companion_at=time.time();self.companion_error=None
                    result={'ok':True,'companion':self.companion,'companion_at':self.companion_at};break
                if raw.startswith(f'COMPANION_ERROR\t{self.seq}\t'.encode()):
                    code=raw.split(b'\t')[-1].decode('ascii',errors='replace')
                    result={'ok':False,'error':code if code in ('invalid','busy') else 'invalid_companion_reply'};break
                if raw==b'ERROR\tcommand':
                    result={'ok':False,'error':'firmware_update_required'};break
            if not result['ok']:
                if result['error']=='confirmation_timeout':self.disconnect()
                self.companion_error=result['error']
        except (OSError,RuntimeError,ValueError):
            self.disconnect();self.companion_error='device_unavailable';result={'ok':False,'error':'device_unavailable'}
        finally:
            if command:command.finish(result)
            self.status('connected' if self.link else 'waiting_ble' if self.transport!='usb' else 'waiting_usb',self.last_data_ok)

    def maintain_actions(self, stop=None):
        from task_actions import parse_action, open_pending
        if not self.control or not self.link or self.baseline_pending or not self.device or self.device.get('firmware') not in ('0.40','0.41','0.42','0.43','0.44','0.45','0.46','0.47','0.48'):return
        if time.monotonic()-self.last_action_query<.8:return
        self.last_action_query=time.monotonic();self.seq+=1
        mode='poll' if self.actions_armed else 'arm'
        try:
            self.link.write(f'ACTION_GET\t{self.seq}\t{mode}\n'.encode())
            deadline=time.monotonic()+2.5
            while time.monotonic()<deadline and not (stop and stop.is_set()):
                raw=self.link.readline().strip()
                if not raw.startswith(f'ACTION\t{self.seq}\t'.encode()):continue
                event=parse_action(raw,self.seq)
                self.actions_armed=True
                if event is None:return
                event_id,thread_id=event
                # 断线重新 arm 时丢弃旧意图；消费后不重试打开，即使回执丢失。
                if mode=='arm' or event_id<=self.last_action_id:return
                self.last_action_id=event_id
                state=self.presence.snapshot()[0] if self.presence else 'unknown'
                outcome=open_pending(self.source,thread_id,state) if self.last_data_ok else 'failed'
                if stop and stop.is_set():return
                self.seq+=1
                self.link.write(f'ACTION_RESULT\t{self.seq}\t{event_id}\t{outcome}\n'.encode())
                deadline=time.monotonic()+2.5
                while time.monotonic()<deadline and not (stop and stop.is_set()):
                    if self.link.readline().strip()==f'ACTION_ACK\t{self.seq}'.encode():return
                break
            self.disconnect()
        except (OSError,RuntimeError,ValueError):
            self.disconnect()

    def step(self, stop=None):
        from monitor import sync_packet
        import serial
        now = time.time()
        if self.last_cycle is not None and (now - self.last_cycle > 12 or now < self.last_cycle):
            self.disconnect()  # 睡眠或时钟跳变后重新建立通知基线。
            self.next_connect_at=0
        self.last_cycle = now
        data_ok = True
        try:
            self.tasks = self.source.snapshot()
            self.last_good_at=now
        except (OSError, sqlite3.Error, ValueError):
            data_ok = False
            self.tasks = [dict(t, state='unknown', mood='idle', done_key='', wait_key='', wait_reason='', result_hint='', progress_hint='') for t in self.tasks]
        if data_ok and not self.last_data_ok:
            self.gate.reset()
            self.baseline_pending=True
        self.last_data_ok = data_ok
        presence=self.presence.snapshot()[0] if self.presence else 'unknown'
        self.extras.observe(self.tasks,presence,data_ok,now)
        try:
            if self.link is None:
                if time.monotonic()<self.next_connect_at:return
                self.next_connect_at=time.monotonic()+2
                ble_error=None
                if self.transport in ('ble','auto') and self.ble_device:
                    from ble_link import BleLink
                    candidate=(self.ble_factory or BleLink)(self.ble_helper,self.ble_device,self.ble_key_file)
                    try:
                        candidate.open();self.link=candidate;self.link_transport='ble'
                    except RuntimeError as exc:
                        candidate.close();ble_error=str(exc)
                if self.link is None:
                    if self.transport=='ble':
                        self.status('waiting_ble',data_ok,ble_error or 'ble_binding_missing');return
                    port=self.port if self.port!='auto' else select_port(self.port_provider(),self.serial_number)
                    if not port:
                        self.status('waiting_ble' if self.transport=='auto' else 'waiting_usb',data_ok,ble_error);return
                    candidate=self.serial_factory()
                    candidate.port,candidate.baudrate=port,115200
                    candidate.timeout,candidate.write_timeout=.2,2
                    candidate.dtr=candidate.rts=False;candidate.exclusive=True
                    candidate.open();self.link=candidate;self.link_transport='usb'
                self.last_ack=time.monotonic()
                self.baseline_pending=True
            filtered=self.gate.filter(self.tasks)
            supports_reasons=bool(self.device_supported and self.device and self.device.get('firmware') in ('0.28','0.29','0.30','0.32','0.33','0.34','0.35','0.36','0.37','0.38','0.39','0.40','0.41','0.42','0.43','0.44','0.45','0.46','0.47','0.48'))
            supports_results=bool(supports_reasons and self.device.get('firmware') in ('0.29','0.30','0.32','0.33','0.34','0.35','0.36','0.37','0.38','0.39','0.40','0.41','0.42','0.43','0.44','0.45','0.46','0.47','0.48'))
            supports_progress=bool(supports_results and self.device.get('firmware') in ('0.38','0.39','0.40','0.41','0.42','0.43','0.44','0.45','0.46','0.47','0.48'))
            signature=(data_ok,supports_reasons,supports_results,supports_progress,tuple(tuple(t.get(k,'') for k in ('id','title','state','done_key','wait_key','mood','wait_reason','result_hint','progress_hint')) for t in filtered))
            # 每 200ms 检查变化；无变化只保留 5 秒一次心跳。
            if not self.baseline_pending and signature==self.sent_signature and time.monotonic()-self.last_sent_at<5:
                self.maintain_voice(stop)
                self.maintain_device(stop)
                self.maintain_companion(stop)
                self.maintain_note(stop)
                self.maintain_actions(stop)
                self.extras.maintain(self,stop)
                return
            if self.baseline_pending:
                self.actions_armed=False
                self.last_action_id=0
            self.seq += 1
            local = dt.datetime.now()
            seconds = local.hour * 3600 + local.minute * 60 + local.second
            good=dt.datetime.fromtimestamp(self.last_good_at) if self.last_good_at else None
            good_seconds=good.hour*3600+good.minute*60+good.second if good else None
            age=max(0,now-self.last_good_at) if self.last_good_at else 0
            sent_at=time.monotonic()
            self.link.write(sync_packet(self.seq,filtered,data_ok,seconds,good_seconds,age,self.baseline_pending,supports_reasons,supports_results,supports_progress))
            deadline, ack = time.monotonic() + (6 if self.link_transport=="ble" else 2), False
            while time.monotonic() < deadline and not (stop and stop.is_set()):
                reply = self.link.readline().strip()
                if reply == f'ACK\t{self.seq}'.encode():
                    self.last_ack, ack = time.monotonic(), True
                    self.ack_ms=round((self.last_ack-sent_at)*1000,1)
                    self.last_sent_at=self.last_ack
                    self.sent_signature=signature
                    self.baseline_pending=False
                    break
                if reply.startswith((b'NOTICE\t', b'MOTION\t', b'PET\t')):
                    self.log.info(reply[:240].decode('ascii', errors='replace'))
            self.status('connected' if ack else 'waiting_ack', data_ok)
            if ack:
                self.maintain_voice(stop)
                self.maintain_device(stop)
                self.maintain_companion(stop)
                self.maintain_note(stop)
                self.maintain_actions(stop)
                self.extras.maintain(self,stop)
            if time.monotonic() - self.last_ack > 15:
                self.disconnect()
        except (OSError, serial.SerialException, RuntimeError) as exc:
            self.disconnect()
            # 不记录会话名、聊天正文或数据库查询内容。
            self.status('waiting_ble' if self.transport!='usb' else 'waiting_usb', data_ok, str(exc) if type(exc).__name__=='BleError' else type(exc).__name__)


def run(source, runtime_dir, port='auto', serial_number=None, transport='usb', ble_device=None, ble_key_file=None, ble_helper=None):
    directory = Path(runtime_dir)
    with single_instance(directory):
        stop = threading.Event()
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: stop.set())
        log = logging.getLogger('weiguang')
        log.setLevel(logging.INFO)
        handler = RotatingFileHandler(directory / 'bridge.log', maxBytes=512_000, backupCount=2, encoding='utf-8')
        os.chmod(directory / 'bridge.log', 0o600)
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        log.addHandler(handler)
        from presence import MacPresence
        bridge = Bridge(source, directory, port, serial_number, logger=log, transport=transport, presence=MacPresence(),
                        ble_device=ble_device,ble_key_file=ble_key_file,ble_helper=ble_helper)
        from control import ControlServer
        try:control=ControlServer(directory).start()
        except OSError:
            control=None;log.error('控制台本机入口不可用，继续任务同步')
        bridge.control=control
        try:
            while not stop.is_set():
                bridge.step(stop)
                stop.wait(.2)
        except Exception as exc:
            try:bridge.diagnostics.service_error({'error':type(exc).__name__})
            except (OSError,ValueError,TypeError):pass
            log.exception('同步进程异常，等待系统重新启动')
            raise
        finally:
            if control:control.close()
            bridge.disconnect()
            bridge.status('stopped', bridge.last_data_ok)
            log.removeHandler(handler)
            handler.close()
