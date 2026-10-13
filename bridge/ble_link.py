"""Core Bluetooth 原生子进程的串口形状适配器，不读取或记录任务正文。"""
import base64
import collections
import json
import os
from pathlib import Path
import select
import subprocess
import time

class BleError(RuntimeError):
    pass

class BleLink:
    def __init__(self, helper, device, key_file):
        self.helper,self.device,self.key_file=map(str,(helper,device,key_file))
        self.port='ble:'+device
        self.process=None
        self.buffer=b''
        self.replies=collections.deque()
        self.timeout=.2

    def event(self, timeout):
        deadline=time.monotonic()+timeout
        while True:
            if b'\n' in self.buffer:
                raw,self.buffer=self.buffer.split(b'\n',1)
                try: event=json.loads(raw)
                except (ValueError,UnicodeError):raise BleError('ble_helper_protocol') from None
                if event.get('event')=='error':raise BleError(event.get('code','ble_error'))
                return event
            if self.process.poll() is not None:raise BleError('ble_helper_stopped')
            remaining=deadline-time.monotonic()
            if remaining<=0:return None
            if select.select([self.process.stdout],[],[],remaining)[0]:
                data=os.read(self.process.stdout.fileno(),8192)
                if not data:raise BleError('ble_helper_stopped')
                self.buffer+=data
                if len(self.buffer)>32768:raise BleError('ble_helper_overflow')

    def open(self):
        if not Path(self.helper).is_file() or not Path(self.key_file).is_file():raise BleError('ble_binding_missing')
        self.process=subprocess.Popen([self.helper,'--device',self.device,'--key-file',self.key_file],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
        try:
            end=time.monotonic()+18
            while time.monotonic()<end:
                event=self.event(.5)
                if event and event.get('event')=='ready':return
            raise BleError('ble_connect_timeout')
        except BaseException:
            self.close();raise

    def write(self,data):
        if not self.process:raise BleError('ble_not_open')
        # 一条 SC5 任务快照一帧；串口换行不属于无线负载。
        raw=json.dumps({'data':base64.b64encode(data.rstrip(b'\n')).decode()}).encode()+b'\n'
        self.process.stdin.write(raw)
        return len(data)

    def readline(self):
        if self.replies:return self.replies.popleft()
        event=self.event(self.timeout)
        if event and event.get('event')=='reply':
            try:data=base64.b64decode(event['data'],validate=True)
            except (ValueError,KeyError):raise BleError('ble_reply_invalid') from None
            self.replies.extend(data.splitlines(keepends=True))
        return self.replies.popleft() if self.replies else b''

    def close(self):
        if self.process:
            self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=2)
            for handle in (self.process.stdin,self.process.stdout):handle.close()
            self.process=None
        self.buffer=b'';self.replies.clear()
