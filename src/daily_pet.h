#pragma once
#include <algorithm>
#include <cmath>
#include <stdint.h>
#include "face_expression.h"

// 屏幕表情模块：不引用电机、音频、网络或存储接口。
inline uint32_t dailyRandom(uint32_t& seed){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}

// 轻触沿用害羞表情；连续抚摸 900 ms 后眯眼满足，松手后保留 2.6 秒。
// 短于 150 ms 的感应空隙不打断一次抚摸；触屏和读数异常立即取消。
struct CatPetting {
 bool down=false,seen=false,satisfied=false,recorded=false,fond=false,remember=true;
 uint32_t since=0,lastTouch=0,lastStroke=0,bonded=0;unsigned strokes=0;
 void cancel(){down=seen=satisfied=recorded=false;}
 void setAffection(bool enabled){remember=enabled;if(!enabled)fond=false;}
 void update(int raw,bool screen,uint32_t now){
  if(raw<0||screen){cancel();return;}
  if(raw>0){
   if(!down&&(!seen||uint32_t(now-lastTouch)>150)){since=now;satisfied=false;recorded=false;}
   down=seen=true;lastTouch=now;
   if(uint32_t(now-since)>=120){
    if(!recorded){strokes=strokes>0&&uint32_t(now-lastStroke)<4000?std::min(3u,strokes+1):1;lastStroke=now;recorded=true;}
    if(remember){fond=true;bonded=now;}
    if(strokes>=2)satisfied=true;
   }
   if(uint32_t(now-since)>=900)satisfied=true;
  }else{down=false;if(seen&&uint32_t(now-lastTouch)>=2600)cancel();}
 }
 bool content(uint32_t now)const{return seen&&satisfied&&uint32_t(now-lastTouch)<2600;}
 bool affectionate(uint32_t now)const{return fond&&uint32_t(now-bonded)<120000;}
 bool softBlink(uint32_t now)const{return affectionate(now)&&!down&&uint32_t(now-bonded)>=4000&&(uint32_t(now-bonded)-4000)%20000<1800;}
 // 仅由 USB 显式画面验收调用；不伪造传感器或电机事件。
 void preview(uint32_t now){down=false;seen=satisfied=true;since=lastTouch=now;}
};

enum class DailyKind { none,look,grin,yawn,blink };
enum class DailyContext { idle,working,affectionate };
struct DailyFrame { FacePose pose;float x=0,y=0; };
struct DailyAnimator {
 DailyKind kind=DailyKind::none;
 uint32_t since=0,quietSince=0,waitMs=45000,seed=7;
 int frequency=1;
 DailyKind last=DailyKind::none;DailyContext situation=DailyContext::idle;bool initialized=false;
 static const char* name(DailyKind k){return k==DailyKind::look?"look":k==DailyKind::grin?"grin":k==DailyKind::yawn?"yawn":k==DailyKind::blink?"blink":"none";}
 static uint32_t duration(DailyKind k){return k==DailyKind::look?3200:k==DailyKind::grin?2600:k==DailyKind::blink?2200:3800;}
 static bool allowed(DailyKind k,DailyContext context){return context==DailyContext::working?(k==DailyKind::look||k==DailyKind::blink):context==DailyContext::affectionate?k!=DailyKind::yawn:true;}
 DailyKind choose(DailyContext context){
  // 权重随情境变化，排除刚播过的一项；不固定轮播，不连续重复。
  int weights[]={4,3,1,3};
  if(context==DailyContext::working){weights[0]=2;weights[1]=weights[2]=0;weights[3]=5;}
  if(context==DailyContext::affectionate){weights[0]=2;weights[1]=6;weights[2]=0;weights[3]=4;}
  int total=0;for(int i=0;i<4;i++){if(DailyKind(i+1)==last)weights[i]=0;total+=weights[i];}
  int pick=dailyRandom(seed)%total;
  for(int i=0;i<4;i++){if(pick<weights[i])return DailyKind(i+1);pick-=weights[i];}
  return DailyKind::blink;
 }
 void cancel(uint32_t now){kind=DailyKind::none;quietSince=now;initialized=true;}
 uint32_t minWait()const{return frequency==0?180000:frequency==2?20000:45000;}
 uint32_t spread()const{return frequency==0?120000:frequency==2?20000:45000;}
 void configure(int level,uint32_t now){if(level<0||level>2||level==frequency)return;frequency=level;cancel(now);waitMs=minWait();}
 void tick(uint32_t now,bool eligible,DailyContext context=DailyContext::idle){
  situation=context;
  if(!initialized){cancel(now);return;}
  if(!eligible){cancel(now);return;}
  if(kind!=DailyKind::none&&!allowed(kind,context)){cancel(now);return;}
  if(kind!=DailyKind::none){
   if(uint32_t(now-since)>=duration(kind)){cancel(now);waitMs=minWait()+dailyRandom(seed)%(spread()+1);}
  }else if(uint32_t(now-quietSince)>=waitMs){kind=choose(context);last=kind;since=now;}
 }
 DailyFrame frame(FacePose base,uint32_t now)const{
  DailyFrame out;out.pose=base;if(kind==DailyKind::none)return out;
  float t=std::min(1.0f,uint32_t(now-since)/float(duration(kind)));
  float blend=std::pow(std::sin(t*3.14159265f),2.0f);
  if(kind==DailyKind::look){out.x=(situation==DailyContext::working?3:7)*std::sin(t*6.2831853f)*blend;out.y=(situation==DailyContext::working?-.4f:-1)*blend;}
  else if(kind==DailyKind::grin)out.pose=mixPose(base,poseFor(FaceMood::joy),blend);
  else if(kind==DailyKind::blink){auto blink=base;blink.eyeHeight=1;blink.eyeCurve=2;out.pose=mixPose(base,blink,blend);}
  else{auto sleepy=poseFor(FaceMood::rest);sleepy.mouthWidth=6;sleepy.mouthOpen=10;out.pose=mixPose(base,sleepy,blend);out.y=-2*blend;}
  return out;
 }
};
