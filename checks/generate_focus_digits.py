"""生成微光原创细线数字的 4-bit 抗锯齿字形；无外部字体或运行依赖。"""
from pathlib import Path
import math

# 38×72 网格，圆润的几何笔画；数字使用相同字宽，冒号独立留白。
PATHS = [
 [('M',19,5),('C',7,5,4,17,4,36),('C',4,55,7,67,19,67),('C',31,67,34,55,34,36),('C',34,17,31,5,19,5)],
 [('M',9,16),('L',22,5),('L',22,67)],
 [('M',5,18),('C',6,9,12,5,20,5),('C',29,5,34,11,34,20),('C',34,29,28,34,21,41),('L',4,67),('L',34,67)],
 [('M',5,12),('C',10,7,15,5,21,5),('C',29,5,34,10,34,20),('C',34,30,27,35,18,35),('C',29,35,35,41,35,51),('C',35,61,29,67,19,67),('C',12,67,7,65,3,61)],
 [('M',27,5),('L',3,46),('L',35,46),('M',28,28),('L',28,67)],
 [('M',33,5),('L',7,5),('L',5,34),('C',10,31,15,30,20,30),('C',29,30,35,36,35,48),('C',35,61,28,67,19,67),('C',12,67,7,65,3,61)],
 [('M',31,9),('C',27,6,24,5,20,5),('C',8,5,4,21,4,40),('C',4,58,8,67,19,67),('C',29,67,34,59,34,48),('C',34,37,29,31,20,31),('C',12,31,6,36,4,43)],
 [('M',3,5),('L',35,5),('L',12,67)],
 [('M',19,5),('C',9,5,4,11,4,20),('C',4,29,11,34,19,35),('C',29,36,35,42,35,51),('C',35,61,29,67,19,67),('C',9,67,3,61,3,51),('C',3,42,9,36,19,35),('C',27,34,34,29,34,20),('C',34,11,29,5,19,5)],
 [('M',34,29),('C',32,37,27,41,19,41),('C',9,41,4,34,4,23),('C',4,12,9,5,19,5),('C',30,5,34,14,34,32),('C',34,51,30,67,18,67),('C',14,67,10,66,6,63)],
 [('M',8,26),('L',8,26),('M',8,48),('L',8,48)],
]

def raster(path, scale, width, height):
    pixels=[0]*(width*height)
    radius=1.35*scale
    def line(a,b):
        ax,ay=a[0]*scale,a[1]*scale;bx,by=b[0]*scale,b[1]*scale
        dx,dy=bx-ax,by-ay;length=dx*dx+dy*dy
        for y in range(max(0,math.floor(min(ay,by)-radius-1)),min(height,math.ceil(max(ay,by)+radius+1))):
            for x in range(max(0,math.floor(min(ax,bx)-radius-1)),min(width,math.ceil(max(ax,bx)+radius+1))):
                t=max(0,min(1,((x+.5-ax)*dx+(y+.5-ay)*dy)/length)) if length else 0
                distance=math.hypot(x+.5-ax-t*dx,y+.5-ay-t*dy)
                alpha=round(15*max(0,min(1,radius+.5-distance)))
                pixels[y*width+x]=max(pixels[y*width+x],alpha)
    cursor=(0,0)
    for op in path:
        if op[0]=='M':cursor=op[1:];continue
        if op[0]=='L':line(cursor,op[1:]);cursor=op[1:];continue
        a=cursor;b=op[1:3];c=op[3:5];d=op[5:7]
        for i in range(1,33):
            t=i/32;u=1-t
            point=tuple(u*u*u*a[k]+3*u*u*t*b[k]+3*u*t*t*c[k]+t*t*t*d[k] for k in (0,1))
            line(cursor,point);cursor=point
    return pixels

def generate():
    lines=['#pragma once','#include <stdint.h>','// 由 checks/generate_focus_digits.py 生成；原创字形，不依赖第三方字体。','namespace FocusDigits {']
    for name,scale in [('large',1),('compact',.70)]:
        w,h,cw=round(38*scale),round(72*scale),round(16*scale)
        data=[];offsets=[]
        for index,path in enumerate(PATHS):
            offsets.append(len(data));pixels=raster(path,scale,cw if index==10 else w,h)
            if len(pixels)%2:pixels.append(0)
            data.extend((pixels[i]<<4)|pixels[i+1] for i in range(0,len(pixels),2))
        lines += [f'static constexpr int {name}Width={w},{name}Height={h},{name}Colon={cw};',f'static constexpr uint16_t {name}Offsets[]={{'+','.join(map(str,offsets))+'};',f'static constexpr uint8_t {name}[]={{']
        lines += [','.join(f'0x{x:02x}' for x in data[i:i+32])+',' for i in range(0,len(data),32)]
        lines += ['};']
    lines += ['}']
    return '\n'.join(lines)+'\n'

if __name__=='__main__':
    target=Path(__file__).resolve().parents[1]/'src/focus_digits.h'
    target.write_text(generate())
    print(f'已生成 {target.name}')
