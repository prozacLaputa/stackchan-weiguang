#pragma once
#include <stdint.h>
#include <algorithm>
#include <cmath>
#include "face_expression.h"
// Short lease: losing the camera/client cannot leave the robot staring forever.
struct VisualFace {
 uint32_t at=0,smileAt=0,requestedAt=0,lastDraw=0; bool valid=false,smiling=false,pending=false;
 int requestedEvent=0,shownEvent=0;
 float x=0,y=0,targetX=0,targetY=0;
 void clear(){valid=false;smiling=pending=false;x=y=targetX=targetY=0;shownEvent=requestedEvent=0;}
 bool active(uint32_t now)const{return valid&&uint32_t(now-at)<1800;}
 // Called only when the renderer can show the visual expression. A task
 // celebration must not consume its whole lifetime before it is displayed.
 bool smile(uint32_t now){
  if(!active(now))return false;
  if(pending){
   pending=false;
   if(uint32_t(now-requestedAt)<8000){smiling=true;smileAt=now;shownEvent=requestedEvent;}
  }
  return showing(now);
 }
 bool showing(uint32_t now)const{return active(now)&&smiling&&uint32_t(now-smileAt)<4000;}
 float emphasis(uint32_t now)const{
  if(!showing(now))return 0;
  uint32_t elapsed=now-smileAt;
  return std::min(1.f,std::min(elapsed/250.f,(4000-elapsed)/350.f));
 }
 FacePose response(const FacePose& base,uint32_t now)const{
  auto happy=poseFor(FaceMood::shy);happy.cheek=.8f;
  return mixPose(base,happy,emphasis(now));
 }
 float waveOffset(uint32_t now)const{
  return showing(now)&&shownEvent==2?6*emphasis(now)*sinf(uint32_t(now-smileAt)/350.f):0;
 }
 void animate(uint32_t now){
  if(!active(now))return;
  float fraction=std::min(1.f,uint32_t(now-lastDraw)/160.f);lastDraw=now;
  x+=(targetX-x)*fraction;y+=(targetY-y)*fraction;
 }
 bool accept(int dx,int dy,int event,uint32_t now){
  if(dx<-100||dx>100||dy<-100||dy>100||event<0||event>2)return false;
  if(valid&&!active(now))clear();
  if(!valid)lastDraw=now;
  targetX=dx/100.f*32;targetY=dy/100.f*14;at=now;valid=true;
  if(event){pending=true;requestedAt=now;requestedEvent=event;}return true;
 }
};
