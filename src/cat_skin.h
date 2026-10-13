#pragma once
#include "face_expression.h"
#include <cmath>

// 猫系只是同一表情姿态的另一种画法；不改变交互、亮度或动作。
template<class Canvas> void catStroke(Canvas& canvas,int x1,int y1,int x2,int y2,uint16_t ink){
 int steps=std::max(std::abs(x2-x1),std::abs(y2-y1));
 for(int i=0;i<=steps;i++){
  float t=steps?i/float(steps):0;
  canvas.fillCircle(int(lroundf(x1+(x2-x1)*t)),int(lroundf(y1+(y2-y1)*t)),1,ink);
 }
}
template<class Canvas> void drawCatSkin(Canvas& canvas,const FacePose& p,int cx,int cy,float open,int breathing,uint32_t now,uint16_t ink){
 for(int side:{-1,1}){
  int x=cx+side*56,ear=cy-29+breathing;
  int relaxed=int(lroundf(p.cheek*2+std::max(0.0f,-p.eyeCurve)*.4f));
  catStroke(canvas,x+side*13,ear+1,x+side*5,ear-14+relaxed,ink);
  catStroke(canvas,x+side*5,ear-14+relaxed,x-side*8,ear-1,ink);
  int y=cy+3+breathing+int(lroundf(side<0?p.leftLift:p.rightLift));
  float curve=(2+p.eyeCurve)*open-2*(1-open);
  for(int dx=-13;dx<=13;dx++){
   float u=dx/13.0f;
   canvas.fillCircle(x+dx,y+int(lroundf(curve*(u*u-.55f))),1,ink);
  }
  if(p.brow>.05f){
   int extent=int(lroundf(6*p.brow));
   catStroke(canvas,x-extent,y-11,x+extent,y-13,ink);
  }
 }
 int my=cy+24+breathing;
 if(p.mouthOpen>1.5f){
  int width=std::max(3,std::min(6,int(lroundf(p.mouthWidth*.5f))));
  int height=std::max(2,std::min(5,int(lroundf(p.mouthOpen*.65f))));
  canvas.drawEllipse(cx,my,width,height,ink);
 }else{
  int width=std::max(7,std::min(11,int(lroundf(p.mouthWidth*.35f))));
  float curve=std::max(2.0f,std::min(4.0f,p.mouthCurve*.7f));
  for(int x=-width;x<=width;x++)canvas.fillCircle(cx+x,my+int(lroundf(curve*(1-x*x/float(width*width)))),1,ink);
 }
 if(p.cheek>.05f){
  uint16_t pink=canvas.color565(int(220*p.cheek),int(145*p.cheek),int(140*p.cheek));
  for(int side:{-1,1})for(int j=-1;j<=1;j++){
   int x=cx+side*84+j*5;catStroke(canvas,x-1,my-7,x+2,my-2,pink);
  }
 }
 if(p.dots>.05f)for(int i=0;i<3;i++){
  float glow=p.dots*(.35f+.65f*((now/500)%3==unsigned(i)));
  canvas.fillCircle(cx+(i-1)*9,cy-38+breathing,1,canvas.color565(int(120*glow),int(175*glow),int(185*glow)));
 }
}
