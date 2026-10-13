#pragma once
#include <algorithm>
#include <cmath>
#include <stdint.h>
#include "focus_digits.h"

namespace FocusDial {
inline float remainingRatio(uint32_t totalSeconds,uint32_t usedMs){
 if(!totalSeconds)return 1.0f;
 return 1.0f-std::min(1.0f,usedMs/(totalSeconds*1000.0f));
}
inline uint16_t ink(int r,int g,int b){return uint16_t((r>>3)<<11|(g>>2)<<5|(b>>3));}
inline float cover(float distance,float radius){return std::max(0.0f,std::min(1.0f,radius+.5f-distance));}
// 固定字宽，抗锯齿细笔画；字符不会随着秒数变化左右跳动。
template<class Canvas> void digits(Canvas& canvas,uint32_t seconds,int centerY,bool compact,bool done){
 using namespace FocusDigits;
 int w=compact?compactWidth:largeWidth,h=compact?compactHeight:largeHeight;
 int cw=compact?compactColon:largeColon,gap=compact?2:3;
 auto data=compact?FocusDigits::compact:large;auto offsets=compact?compactOffsets:largeOffsets;
 seconds=std::min(uint32_t(5999),seconds);
 int glyphs[]={int(seconds/600),int(seconds/60%10),10,int(seconds%60/10),int(seconds%10)};
 int x=(320-(4*w+cw+4*gap))/2,y=centerY-h/2;
 for(int glyph:glyphs){
  int width=glyph==10?cw:w;const uint8_t* alpha=data+offsets[glyph];
  for(int py=0;py<h;py++)for(int px=0;px<width;px++){
   int i=py*width+px,a=(alpha[i/2]>>(i%2?0:4))&15;
   if(a)canvas.drawPixel(x+px,y+py,ink((done?151:232)*a/15,(done?207:237)*a/15,(done?183:235)*a/15));
  }
  x+=width+gap;
 }
}
// 从十二点开始顺时针读取剩余比例，底环始终完整；仅在细环附近做像素运算。
template<class Canvas> void ring(Canvas& canvas,float remaining,bool compact,bool paused,bool waiting=false,bool rest=false){
 const float pi=3.14159265358979323846f;
 int cy=compact?(waiting?110:108):120;float radius=compact?(waiting?68.0f:69.0f):105.0f,half=compact?1.2f:1.45f;
 remaining=std::max(0.0f,std::min(1.0f,remaining));
 float end=2*pi*remaining,ex=radius*std::sin(end),ey=-radius*std::cos(end);
 int bound=int(std::ceil(radius+half+1));
 float outer=(radius+half+.5f)*(radius+half+.5f),inner=(radius-half-.5f)*(radius-half-.5f);
 for(int dy=-bound;dy<=bound;dy++)for(int dx=-bound;dx<=bound;dx++){
  float square=float(dx*dx+dy*dy);if(square>outer||square<inner)continue;
  float track=cover(std::abs(std::sqrt(square)-radius),half),arc=0;
  if(remaining>=1)arc=track;
  else if(remaining>0){
   float angle=std::atan2(float(dx),float(-dy));if(angle<0)angle+=2*pi;
   if(angle<=end)arc=track;
   arc=std::max(arc,cover(std::hypot(float(dx)-ex,float(dy)-ey),half));
   arc=std::max(arc,cover(std::hypot(float(dx),float(dy)+radius),half));
  }
  float background=track*(1-arc);
  int r=int(24*background+(paused?116:rest?133:134)*arc),g=int(34*background+(paused?135:rest?170:196)*arc),b=int(32*background+(paused?130:rest?205:173)*arc);
  if(r||g||b)canvas.drawPixel(160+dx,cy+dy,ink(r,g,b));
 }
}
}
