"""Explicit USB camera session. Images stay in pipes/RAM; no credentials/cloud/audio."""
import argparse
import base64
import collections
import json
import math
import os
from pathlib import Path
import select
import signal
import subprocess
import time


class Interaction:
    def __init__(self):
        self.seen=0; self.last_face=None; self.last_greet=-100.;self.last_wave=-100.
        self.hand=collections.deque(); self.x=0.; self.y=0.

    def update(self, observation, now):
        face=observation.get('face') if observation.get('faces')==1 else None
        if not self.point(face):
            self.seen=0; self.hand.clear()
            return None, '画面里有多人，暂不跟随。' if observation.get('faces',0)>1 else '等你出现在镜头前…'
        self.seen+=1
        away=self.last_face is None or now-self.last_face>=4
        if away:self.seen=1
        event=0
        # Do not greet a single false-positive, or re-greet on brief occlusion.
        if self.seen>=3 and now-self.last_greet>=30 and (self.last_face is None or getattr(self,'arrival',False)):
            event=1; self.last_greet=now; self.arrival=False
        if away:self.arrival=True
        self.last_face=now
        self.x,self.y=face
        hand=observation.get('hand')
        if self.point(hand):self.hand.append((now,hand[0]))
        while self.hand and now-self.hand[0][0]>2.5:self.hand.popleft()
        message='看到你了 · 视线跟随中'
        if self.seen>=3 and now-self.last_wave>=8 and len(self.hand)>=4:
            xs=[p[1] for p in self.hand]
            # Open hand + a deliberate reversal, not a stationary palm or one pass.
            directions=[b-a for a,b in zip(xs,xs[1:]) if abs(b-a)>.035]
            if max(xs)-min(xs)>.16 and any(a*b<0 for a,b in zip(directions,directions[1:])):
                event=2;self.last_wave=now;self.hand.clear();message='看到你挥手啦 · 回一个笑脸'
        if self.seen<3:return None,'好像看到你了…'
        return (round((self.x-.5)*200),round((.5-self.y)*200),event),message

    @staticmethod
    def point(value):
        return isinstance(value,list) and len(value)==2 and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in value)


def emit(message,**values):
    print(json.dumps(dict(message=message,**values),ensure_ascii=False),flush=True)


def display_feedback(ack):
    # Recognition alone does not prove that the robot is showing a response.
    state=ack.decode('ascii',errors='replace').split('\t')[1:]
    return {
        'tracking':'看到你了 · 视线跟随中',
        'smiling':'正在向你微笑',
        'queued':'看到你了 · 正准备回应',
        'page':'看到你了 · 回到机器人主屏可看互动',
        'rest':'看到你了 · 机器人正在休息',
        'touch':'看到你了 · 等摸头或触屏动作结束',
        'voice':'看到你了 · 语音表情优先',
        'animation':'看到你了 · 等当前表情结束后回应',
        'task':'看到你了 · 待回应任务提示优先',
        'clear':'等待稳定识别…',
    }.get(state[0] if state else '', '识别到你了 · 设备显示状态待确认')


class Camera:
    def __init__(self,port):
        import serial
        class NoResetSerial(serial.Serial):
            # ESP32-S3 native USB treats DTR/RTS transitions as reset/download.
            # pyserial's two separate line writes can pulse reset even with both False.
            # This session only transports bytes; leave both control lines untouched.
            def _update_dtr_state(self):pass
            def _update_rts_state(self):pass
        self.link=NoResetSerial(port,baudrate=115200,timeout=.12,write_timeout=.5,exclusive=True)
        self.link.reset_input_buffer()
        self.seq=0;self.buffer=bytearray()

    def readline(self,deadline):
        # Serial.readLine(timeout) may return half a line during BLE/UI work.
        # Keep partial packets across reads; only consume newline-terminated data.
        pumped=time.monotonic()
        while time.monotonic()<deadline:
            end=self.buffer.find(b'\n')
            if end>=0:
                raw=bytes(self.buffer[:end]).rstrip(b'\r');del self.buffer[:end+1]
                return raw
            chunk=self.link.read(min(1024,max(1,self.link.in_waiting)))
            self.buffer.extend(chunk)
            if len(self.buffer)>8192:raise RuntimeError('serial_overflow')
            if not chunk and time.monotonic()-pumped>=.18:
                # Bundled HWCDC occasionally holds a short final TX packet until
                # another host request. PING advances it without replaying CAM_GET
                # or any effect. READY lines are safely ignored by callers.
                self.link.write(b'PING\n');pumped=time.monotonic()
        return b''

    def line(self,command,prefix,timeout=3):
        self.link.write((command+'\n').encode());end=time.monotonic()+timeout
        while time.monotonic()<end:
            raw=self.readline(end)
            if raw.startswith(prefix):return raw
            if raw.startswith(b'CAM_ERROR'):raise RuntimeError('camera_error')
        raise RuntimeError('camera_timeout')

    def frame(self):
        self.seq+=1
        header=self.line('CAM_GET\t'+str(self.seq),b'CAM_FRAME\t').split(b'\t')
        if len(header)!=3 or int(header[1])!=self.seq:raise RuntimeError('frame_header')
        size=int(header[2])
        if not 100<=size<=65536:raise RuntimeError('frame_size')
        data=bytearray();end=time.monotonic()+3
        while len(data)<size and time.monotonic()<end:
            parts=self.readline(end).split(b'\t')
            if parts[0]!=b'CAM_DATA':continue
            if len(parts)!=4 or int(parts[1])!=self.seq or int(parts[2])!=len(data):raise RuntimeError('frame_chunk')
            chunk=base64.b64decode(parts[3],validate=True)
            if not 1<=len(chunk)<=384 or len(data)+len(chunk)>size:raise RuntimeError('frame_chunk')
            data+=chunk
        if len(data)!=size or data[:2]!=b'\xff\xd8' or data[-2:]!=b'\xff\xd9':
            error=RuntimeError('frame_incomplete')
            error.metrics={'received':len(data),'expected':size,'jpeg_start':data[:2]==b'\xff\xd8','jpeg_end':data[-2:]==b'\xff\xd9','buffered':len(self.buffer)}
            raise error
        return bytes(data)

    def close(self):
        try:self.line('CAM_STOP',b'CAM_OFF',1)
        except Exception:pass # Firmware lease stops capture independently of this process.
        self.link.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--analyzer',required=True);parser.add_argument('--seconds',type=float,default=0)
    args=parser.parse_args()
    from serial.tools import list_ports
    from runtime import select_port
    from presence import SessionReader
    root=Path.home()/'Library/Application Support/Weiguang'
    config=json.loads((root/'config.json').read_text())
    if config.get('transport')!='ble':raise RuntimeError('ble_required')
    def live():
        state=json.loads((root/'runtime/status.json').read_text())
        age=time.time()-(root/'runtime/status.json').stat().st_mtime
        return 0<=age<10 and state.get('connection')=='connected' and state.get('transport')=='ble'
    if not live():raise RuntimeError('ble_required')
    port=select_port(list_ports.comports(),config.get('serial_number'))
    if not port:raise RuntimeError('usb_required')
    parent=os.getppid();stopped=False
    def stop(*_):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    session=SessionReader();camera=None;analyzer=None
    try:
        current=session()
        if current!='awake':raise RuntimeError('session_unknown' if current=='unknown' else 'session_inactive')
        camera=Camera(port)
        identity=camera.line('PING',b'READY\t').decode().split('\t')[-1]
        if identity!=config.get('ble_device'):raise RuntimeError('device_mismatch')
        if camera.line('CAM_INFO',b'CAM_CAP\t').split(b'\t')[1]!=b'1':raise RuntimeError('firmware_required')
        camera.line('CAM_START',b'CAM_OK')
        analyzer=subprocess.Popen([args.analyzer,'--vision-analyze'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
        interaction=Interaction();started=time.monotonic();frames=0;previous=None
        while not stopped and os.getppid()==parent and (not args.seconds or time.monotonic()-started<args.seconds):
            begin=time.monotonic()
            current=session()
            if current!='awake':raise RuntimeError('session_unknown' if current=='unknown' else 'session_inactive')
            if not live():raise RuntimeError('ble_required')
            image=camera.frame()
            analyzer.stdin.write(base64.b64encode(image)+b'\n');image=None
            # Vision's first inference loads the on-device models (~3s measured).
            # Later frames remain bounded to 2s; both fit inside the camera lease.
            if not select.select([analyzer.stdout],[],[],4.2 if frames==0 else 2)[0]:raise RuntimeError('recognition_timeout')
            raw=analyzer.stdout.readline(4096)
            observation=json.loads(raw)
            if observation.get('ok') is not True:raise RuntimeError('recognition_failed')
            if stopped or session()!='awake':break
            pose,message=interaction.update(observation,time.monotonic())
            if pose:message=display_feedback(camera.line('VISUAL\t%d\t%d\t%d'%pose,b'VISUAL_OK',1))
            else:camera.line('VISUAL_CLEAR',b'VISUAL_OK',1)
            frames+=1
            fps=frames/max(.1,time.monotonic()-started)
            emit(message,fps=round(fps,1),faces=observation.get('faces',0),event=pose[2] if pose else 0)
            remaining=.32-(time.monotonic()-begin)
            if remaining>0:time.sleep(remaining)
        emit('视觉互动已关闭。')
    finally:
        if camera:camera.close()
        if analyzer:
            analyzer.terminate()
            try:analyzer.wait(timeout=1)
            except subprocess.TimeoutExpired:analyzer.kill();analyzer.wait()


if __name__=='__main__':
    try:main()
    except Exception as error:
        messages={'usb_required':'请接上 Chan 的 USB 数据线，再开启。','ble_required':'请保持蓝牙任务同步，恢复连接后再开启。',
                  'device_mismatch':'USB 设备与已绑定 Chan 不一致，已停止。','camera_timeout':'摄像头没有及时响应，已停止；请重试或检查固件。',
                  'camera_error':'摄像头启动或采集失败，已停止。','session_inactive':'Mac 已锁定或休息，视觉互动已关闭。',
                  'session_unknown':'无法确认 Mac 会话状态，已停止采集。请从微光控制台开启。',
                  'recognition_timeout':'本地识别超时，摄像头已停止。','recognition_failed':'画面未能完成识别，摄像头已停止。'}
        messages.update({'frame_incomplete':'摄像头画面接收不完整，已停止。请重新开启互动。',
                         'frame_chunk':'摄像头画面分包校验失败，已停止。请重新开启互动。',
                         'frame_header':'摄像头画面序号不一致，已停止。请重新开启互动。',
                         'frame_size':'摄像头画面大小异常，已停止。请重新开启互动。',
                         'serial_overflow':'摄像头通信缓冲异常，已停止。请重新开启互动。'})
        emit(messages.get(str(error),'视觉连接中断，已停止。请检查 USB 后重新开启。'))
        raise SystemExit(1)
