"""Render the actual focus dial with sample data; this is not a hardware screenshot."""
from pathlib import Path
import struct,subprocess,zlib
root=Path(__file__).resolve().parents[1]
out=root/'.runtime/preview';out.mkdir(parents=True,exist_ok=True)
exe=out/'render'
subprocess.run(['clang++','-std=c++11','-Isrc','checks/render_focus_dial.cpp','-o',str(exe)],cwd=root,check=True)
ppm=out/'focus.ppm'
subprocess.run([str(exe),'1125','.75','0',str(ppm)],check=True)
pixels=ppm.read_bytes().split(b'\n',3)[3]
assert len(pixels)==320*240*3
rows=b''.join(b'\0'+pixels[y*960:(y+1)*960] for y in range(240))
def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',320,240,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')
target=root/'docs/preview/focus.png';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(png)
print(target)
