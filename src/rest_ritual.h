#pragma once
#include "face_expression.h"
#include <stdint.h>

// 只编排屏幕姿态；不改变真实休息、触摸、电机或任务状态。
class RestRitual {
public:
 enum Phase { none,fallingAsleep,waking };
 Phase phase=none;
 uint32_t since=0;
private:
 bool wasResting=false;
 FacePose origin=poseFor(FaceMood::idle);
 static FacePose blend(const FacePose& a,const FacePose& b,float t){
  t=std::max(0.0f,std::min(1.0f,t));return mixPose(a,b,t*t*(3-2*t));
 }
 void start(Phase next,const FacePose& current,uint32_t now){origin=current;since=now;phase=next;}
public:
 uint32_t duration()const{return phase==fallingAsleep?3200:2100;}
 bool active(uint32_t now)const{return phase!=none&&uint32_t(now-since)<duration();}
 const char* name(uint32_t now)const{return !active(now)?"none":phase==fallingAsleep?"sleep":"wake";}
 void cancel(){phase=none;}
 FacePose frame(const FacePose& base,uint32_t now)const{
  if(!active(now))return base;
  float t=uint32_t(now-since);
  auto rest=poseFor(FaceMood::rest),half=poseFor(FaceMood::idle);
  half.eyeHeight=4;half.eyeCurve=-1;half.mouthWidth=20;half.mouthCurve=3;
  if(phase==fallingAsleep){
   auto yawn=rest;yawn.mouthWidth=6;yawn.mouthOpen=7;
   if(t<600)return blend(origin,half,t/600);
   if(t<1700)return blend(half,yawn,(t-600)/1100);
   if(t<2300)return blend(yawn,half,(t-1700)/600);
   return blend(half,rest,(t-2300)/900);
  }
  half.cheek=.15f;auto blink=half;blink.eyeHeight=1;blink.eyeCurve=2;
  auto shy=poseFor(FaceMood::shy);
  if(t<500)return blend(origin,half,t/500);
  if(t<1050)return blend(half,blink,(t-500)/550);
  if(t<1700)return blend(blink,shy,(t-1050)/650);
  return blend(shy,base,(t-1700)/400);
 }
 void update(bool resting,bool headContact,bool blocked,const FacePose& base,uint32_t now){
  // 即使当前不可展示也消费状态边沿，离开列表/提醒后不补播。
  bool entered=resting&&!wasResting,left=!resting&&wasResting;
  wasResting=resting;
  if(blocked){cancel();return;}
  auto current=frame(base,now);
  if(entered)start(fallingAsleep,current,now);
  else if(left){if(headContact)start(waking,current,now);else cancel();}
  if(!active(now))cancel();
 }
 // USB 显式预览只检查画面，不假造真实触摸或执行动作。
 void previewWake(const FacePose& base,uint32_t now){start(waking,base,now);}
};
