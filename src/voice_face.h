#pragma once
#include "face_expression.h"
#include <cmath>

// Short-lived screen overlay. No audio, servo, page navigation or stored preferences.
class VoiceFace {
 uint32_t received=0,lastFrame=0;
 int level=-1;
 float opening=0;
public:
 bool accept(int next,uint32_t now){
  if(next < -1 || next > 3)return false;
  level=next;received=now;return true;
 }
 bool active(uint32_t now)const{return level>=0&&uint32_t(now-received)<600;}
 int current(uint32_t now)const{return active(now)?level:-1;}
 void clear(){level=-1;opening=0;}
 FacePose frame(const FacePose& base,uint32_t now,bool visible){
  uint32_t dt=std::min(uint32_t(100),uint32_t(now-lastFrame));lastFrame=now;
  if(!visible||!active(now)){opening=0;return base;}
  float target=level*2.4f;
  opening+=(target-opening)*std::min(1.0f,dt/85.0f);
  auto pose=poseFor(FaceMood::idle);
  pose.eyeHeight=7;pose.eyeCurve=2;pose.mouthWidth=opening>1.5f?7:20;
  pose.mouthCurve=4;pose.mouthOpen=opening;pose.cheek=.12f;
  return pose;
 }
};
