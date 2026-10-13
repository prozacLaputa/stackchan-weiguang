"""本机控制队列：面板不直接占用蓝牙，所有设备命令由同步线程顺序发送。"""
import json
import os
from pathlib import Path
import queue
import socket
import socketserver
import threading
import time

RANGES = {'light': 3, 'rest': 4, 'pet': 1, 'wait_motion': 1, 'done_motion': 1, 'daily': 2, 'away_rest': 1, 'greeting': 1, 'affection': 1, 'skin': 1, 'focus_motion': 1}


def valid_note_text(value):
    if not isinstance(value,str) or not 1<=len(value)<=32:return False
    visible=False
    for char in value:
        cp=ord(char)
        if not (0x20<=cp<=0x7e or 0xa0<=cp<=0x24f or 0x2010<=cp<=0x2027 or 0x3000<=cp<=0x303f or 0x4e00<=cp<=0x9fff or 0xff01<=cp<=0xff60):return False
        visible|=cp not in (0x20,0xa0,0x3000)
    return visible


def parse_note(raw,seq):
    parts=raw.decode('ascii').strip().split('\t')
    if len(parts)!=6 or parts[:2]!=['NOTE',str(seq)] or parts[3] not in ('empty','active','done'):raise ValueError('invalid_note_reply')
    revision,error=int(parts[2]),int(parts[5]);encoded=parts[4]
    if not 0<=revision<=4294967295 or error not in (0,1):raise ValueError('invalid_note_reply')
    if encoded=='-':text=''
    else:
        if not 2<=len(encoded)<=192 or len(encoded)%2 or any(c not in '0123456789abcdefABCDEF' for c in encoded):raise ValueError('invalid_note_reply')
        text=bytes.fromhex(encoded).decode('utf-8')
    if (parts[3]=='empty' and (revision or text)) or (parts[3]!='empty' and (not revision or not valid_note_text(text))):raise ValueError('invalid_note_reply')
    return dict(revision=revision,state=parts[3],text=text,save_error=error)


def validate_request(value):
    if not isinstance(value, dict) or value.get('action') not in ('inspect', 'configure', 'focus', 'note'):
        raise ValueError('invalid_request')
    if value['action'] == 'inspect':
        if set(value) != {'action'}: raise ValueError('invalid_request')
        return value
    if value['action'] == 'note':
        operation=value.get('operation')
        if operation=='inspect' and set(value)=={'action','operation'}:return value
        revision=value.get('expected_revision')
        keys={'action','operation','expected_revision'}
        if type(revision) is not int or not 0<=revision<=4294967295:raise ValueError('invalid_request')
        if operation in ('done','restore') and set(value)==keys:return value
        if operation=='set' and set(value)==keys|{'text'} and valid_note_text(value.get('text')):return value
        raise ValueError('invalid_request')
    if value['action'] == 'focus':
        operation=value.get('operation')
        if operation in ('stop','pause','resume','next') and set(value)=={'action','operation'}: return value
        if operation=='start' and set(value)=={'action','operation','minutes'} and type(value['minutes']) is int and value['minutes'] in (15,25,45): return value
        raise ValueError('invalid_request')
    changes = value.get('changes')
    if set(value) != {'action', 'changes'} or not isinstance(changes, dict) or not changes:
        raise ValueError('invalid_request')
    for key, number in changes.items():
        if key not in RANGES or type(number) is not int or not 0 <= number <= RANGES[key]:
            raise ValueError('invalid_request')
    return value


def parse_device(raw, seq):
    parts = raw.decode('ascii').strip().split('\t')
    if len(parts) not in (14,16,25,29,30,31) or parts[:2] != ['DEVICE', str(seq)]: raise ValueError('invalid_device_reply')
    if (parts[2],len(parts)) not in (('0.24',14),('0.25',16),('0.26',16),('0.28',16),('0.29',16),('0.30',25),('0.32',25),('0.33',25),('0.34',25),('0.35',29),('0.36',29),('0.37',30),('0.38',30),('0.39',30),('0.40',30),('0.41',31),('0.42',31),('0.43',31),('0.44',31),('0.45',31),('0.46',31)) or parts[5] not in ('home', 'list', 'settings', 'game', 'focus'): raise ValueError('unsupported_device')
    if parts[5]=='focus' and parts[2] not in ('0.40','0.41','0.42','0.43','0.44','0.45','0.46'): raise ValueError('unsupported_device')
    if parts[5]=='game' and parts[2]!='0.32': raise ValueError('unsupported_device')
    keys = ('battery', 'charging', 'resting', 'brightness', 'light', 'rest', 'pet', 'save_error', 'uptime', 'sync_age')
    numbers = [int(parts[i]) for i in (3, 4, 6, 7, 8, 9, 10, 11, 12, 13)]
    bounds = [(-1,100),(0,1),(0,1),(0,255),(0,3),(0,4),(0,1),(0,1),(0,4294967),(0,4294967)]
    if parts[2] in ('0.25','0.26','0.28','0.29','0.30','0.32','0.33','0.34','0.35','0.36','0.37','0.38','0.39','0.40','0.41','0.42','0.43','0.44','0.45','0.46'):
        keys += ('wait_motion','done_motion')
        numbers += [int(parts[14]),int(parts[15])]
        bounds += [(0,1),(0,1)]
    if any(not low <= number <= high for number, (low, high) in zip(numbers, bounds)):
        raise ValueError('invalid_device_reply')
    device = dict(zip(keys, numbers), firmware=parts[2], page=parts[5])
    if parts[2] in ('0.30','0.32','0.33','0.34','0.35','0.36','0.37','0.38','0.39','0.40','0.41','0.42','0.43','0.44','0.45','0.46'):
        states={'ready','moving','cooldown','disabled','unavailable','screen','release','sensor'}
        results={'none','detected','moving','completed','skipped','stopped','failed'}
        reasons={'none','not-initialized','bus-init','power-init','torque-release','calibration',
                 'position-read','position-range','load-high','release-ack','torque-read','command-ack',
                 'pet-command-ack','feedback-range','pet-follow-error','timeout','not-reached','return-ack',
                 'no-event','disabled','busy','preference','cooldown','already-moving','position-limit',
                 'settling','screen-touch','release-required','head-read','too-short'}
        if parts[16] not in states or parts[17] not in reasons or parts[22] not in results or parts[23] not in reasons:
            raise ValueError('invalid_motion_reply')
        extra = [int(parts[i]) for i in (18,19,20,21,24)]
        limits = [(0,5000),(0,1),(0,4294967295),(0,4294967),(0,1)]
        if any(not low<=n<=high for n,(low,high) in zip(extra,limits)):
            raise ValueError('invalid_motion_reply')
        device.update(zip(('pet_cooldown_ms','head_sensor','pet_event','pet_age','head_down'),extra))
        device.update(motion_state=parts[16],motion_reason=parts[17],pet_result=parts[22],pet_reason=parts[23])
    if parts[2] in ('0.35','0.36','0.37','0.38','0.39','0.40','0.41','0.42','0.43','0.44','0.45','0.46'):
        extra=[int(p) for p in parts[25:29]]
        if any(not 0<=v<=limit for v,limit in zip(extra,(2,1,1,1))):raise ValueError('invalid_device_reply')
        device.update(zip(('daily','away_rest','greeting','affection'),extra))
    if parts[2] in ('0.37','0.38','0.39','0.40','0.41','0.42','0.43','0.44','0.45','0.46'):
        skin=int(parts[29])
        if skin not in (0,1):raise ValueError('invalid_device_reply')
        device['skin']=skin
    if parts[2] in ('0.41','0.42','0.43','0.44','0.45','0.46'):
        focus=int(parts[30])
        if focus not in (0,1):raise ValueError('invalid_device_reply')
        device['focus_motion']=focus
    return device


def parse_companion(raw, seq):
    parts=raw.decode('ascii').strip().split('\t')
    if len(parts) not in (7,10,14) or parts[:2]!=['COMPANION',str(seq)] or parts[2] not in ('awake','away','unknown') or parts[3] not in ('off','running','paused','done'):
        raise ValueError('invalid_companion_reply')
    left,total,welcome=map(int,parts[4:7])
    if not 0<=left<=total<=5400 or welcome not in (0,1): raise ValueError('invalid_companion_reply')
    if (parts[3]=='off' and (left or total)) or (parts[3] in ('running','paused') and (not left or not total)) or (parts[3]=='done' and (left or not total)) or (welcome and parts[2]!='awake'):
        raise ValueError('invalid_companion_reply')
    result=dict(presence=parts[2],focus_state=parts[3],remaining=left,total=total,welcome=welcome)
    if len(parts)>=10:
        stage=parts[7];focus_total,round_number=map(int,parts[8:10])
        if stage not in ('focus','rest') or not 60<=focus_total<=5400 or focus_total%60 or not 0<=round_number<=9999:
            raise ValueError('invalid_companion_reply')
        if parts[3]=='off':
            if stage!='focus' or round_number: raise ValueError('invalid_companion_reply')
        elif not round_number or (stage=='rest' and total!=300) or (stage=='focus' and (total!=focus_total or parts[3]=='done')):
            raise ValueError('invalid_companion_reply')
        result.update(stage=stage,focus_total=focus_total,round=round_number)
    if len(parts)==14:
        day,seconds,rounds,save_error=map(int,parts[10:])
        if (day!=0 and not 10957<=day<=47482) or not 0<=seconds<=86400 or not 0<=rounds<=1440 or save_error not in (0,1) or (day==0 and (seconds or rounds)):
            raise ValueError('invalid_companion_reply')
        result.update(today_day=day,today_seconds=seconds,today_rounds=rounds,summary_save_error=save_error)
    return result


class Command:
    def __init__(self, request):
        self.request = validate_request(request)
        self.expires = time.monotonic() + 3
        self.done = threading.Event()
        self.result = None

    def finish(self, result):
        self.result = result
        self.done.set()


class ControlServer:
    def __init__(self, directory):
        self.path = Path(directory) / 'control.sock'
        self.queue = queue.Queue(maxsize=4)
        self.server = None

    def start(self):
        owner = self
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(2)
                try:
                    raw = self.rfile.readline(2049)
                    if len(raw)>2048 or not raw.endswith(b'\n'): raise ValueError('invalid_request')
                    command = Command(json.loads(raw))
                    owner.queue.put_nowait(command)
                    result = command.result if command.done.wait(4) else {'ok':False,'error':'confirmation_timeout'}
                except queue.Full: result = {'ok':False,'error':'busy'}
                except (ValueError, OSError): result = {'ok':False,'error':'invalid_request'}
                try: self.wfile.write(json.dumps(result).encode()+b'\n')
                except OSError: pass
        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True
        self.path.unlink(missing_ok=True)  # 调用者已持有同步进程单实例锁。
        self.server = Server(str(self.path), Handler)
        self.path.chmod(0o600)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def take(self):
        try: return self.queue.get_nowait()
        except queue.Empty: return None

    def close(self):
        if self.server:
            self.server.shutdown();self.server.server_close();self.thread.join(2)
            self.path.unlink(missing_ok=True)
        while True:
            command = self.take()
            if command is None: break
            command.finish({'ok':False,'error':'service_stopped'})


def request(directory, value):
    validate_request(value)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5)
        client.connect(str(Path(directory)/'control.sock'))
        client.sendall(json.dumps(value).encode()+b'\n')
        data=b''
        while not data.endswith(b'\n'):
            chunk=client.recv(4096)
            if not chunk or len(data)+len(chunk)>8192: raise ValueError('invalid_control_reply')
            data+=chunk
    return json.loads(data)


if __name__ == '__main__':
    import sys
    try:
        value=json.loads(sys.stdin.buffer.read(2049))
        result=request(Path.home()/'Library/Application Support/Weiguang/runtime',value)
    except (OSError, ValueError): result={'ok':False,'error':'service_unavailable'}
    print(json.dumps(result,ensure_ascii=False))
