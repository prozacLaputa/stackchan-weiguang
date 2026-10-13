"""停止 monitor 后使用；从 Chan 读取实际帧缓冲，不模拟任务或触摸。"""
import argparse, datetime as dt, os, struct, sys, time
from pathlib import Path
import serial
from monitor import recent_tasks, choose_tasks, Tail, batch_packet

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--port',default='/dev/cu.usbmodem2101')
ap.add_argument('--output',type=Path,default=Path('.runtime/home.ppm'))
args=ap.parse_args()
s=serial.Serial();s.port=args.port;s.baudrate=115200;s.timeout=.5;s.write_timeout=3;s.dtr=False;s.rts=False;s.open()
try:
 tasks=[]
 for tid,path,title,updated in recent_tasks(Path.home()/'.codex/state_5.sqlite',os.environ.get('CODEX_THREAD_ID')):
  try:state=Tail(path).poll()
  except OSError:state='unknown'
  tasks.append(dict(id=tid,title=title or '未命名任务',state=state,updated=updated))
 tasks=choose_tasks(tasks,os.environ.get('CODEX_THREAD_ID'))
 now=dt.datetime.now();s.write(f'TIME\t{now.hour*3600+now.minute*60+now.second}\n'.encode())
 s.write(batch_packet(9000,tasks));time.sleep(2)
 s.write(b'INFO\nSHOT\n')
 end=time.monotonic()+10
 while time.monotonic()<end:
  line=s.readline()
  if line.startswith(b'FRAME\t'):
   _,w,h=line.decode().strip().split('\t');w,h=int(w),int(h);break
  if line.startswith((b'UI\t',b'HEAD\t',b'ACK\t')):print(line.decode().strip())
 else:raise SystemExit('No FRAME header')
 raw=bytearray();end=time.monotonic()+20
 while len(raw)<w*h*2 and time.monotonic()<end:raw.extend(s.read(w*h*2-len(raw)))
 if len(raw)!=w*h*2:raise SystemExit(f'Incomplete frame: {len(raw)}')
 rgb=bytearray()
 for (c,) in struct.iter_unpack('>H',raw):rgb.extend((((c>>11)&31)*255//31,((c>>5)&63)*255//63,(c&31)*255//31))
 args.output.write_bytes(f'P6\n{w} {h}\n255\n'.encode()+rgb)
 print(f'Captured real device framebuffer {w}x{h}: {args.output}')
finally:s.close()
