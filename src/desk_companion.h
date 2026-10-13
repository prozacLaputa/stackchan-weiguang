#pragma once
#include <algorithm>
#include <stdint.h>
#include <string>

// 只管理界面状态；没有电机、音频或存储依赖。
struct FocusTimer {
 enum Phase { off,running,paused,done };
 Phase phase=off;uint32_t started=0,total=0,ended=0,elapsed=0,completions=0;
 bool active()const{return phase==running||phase==paused;}
 void start(uint32_t seconds,uint32_t now){total=seconds;started=now;elapsed=0;phase=running;}
 void stop(){phase=off;total=elapsed=0;}
 uint32_t used(uint32_t now)const{return std::min(total*1000u,elapsed+(phase==running?uint32_t(now-started):0));}
 void tick(uint32_t now){if(phase==running&&uint32_t(now-started)>=total*1000u-elapsed){phase=done;++completions;ended=started+total*1000u-elapsed;elapsed=total*1000u;}}
 bool pause(uint32_t now){tick(now);if(phase!=running)return false;elapsed=used(now);phase=paused;return true;}
 bool resume(uint32_t now){if(phase!=paused)return false;started=now;phase=running;return true;}
 uint32_t remaining(uint32_t now)const{return active()?(total*1000u-used(now)+999)/1000:0;}
 bool finished(uint32_t now)const{return phase==done&&uint32_t(now-ended)<10000;}
 const char* name()const{return phase==running?"running":phase==paused?"paused":phase==done?"done":"off";}
};
// 专注到时自动休息五分钟；休息结束等待主动开始，不自动累计无人参与的轮次。
struct FocusCycle:FocusTimer {
 enum Stage {work,rest};Stage stage=work;
 uint32_t focusTotal=1500,round=0,focusCompletions=0,lastBoundary=0,lastFocusEnd=0;
 bool boundary=false;
 bool resting()const{return stage==rest;}
 bool working()const{return stage==work&&phase==running;}
 const char* stageName()const{return resting()?"rest":"focus";}
 void start(uint32_t seconds,uint32_t now){focusTotal=seconds;round=1;stage=work;boundary=false;FocusTimer::start(seconds,now);}
 void stop(){FocusTimer::stop();stage=work;round=0;boundary=false;}
 void tick(uint32_t now){
  Phase before=phase;FocusTimer::tick(now);
  if(before!=running||phase!=done)return;
  boundary=true;lastBoundary=ended;
  if(stage==work){
   ++focusCompletions;lastFocusEnd=ended;stage=rest;FocusTimer::start(300,ended);
   // 即使主循环迟到，也按真实截止时刻进入休息；最多推进到休息结束。
   FocusTimer::tick(now);if(phase==done)lastBoundary=ended;
  }
 }
 bool pause(uint32_t now){Stage before=stage;tick(now);return before==stage&&FocusTimer::pause(now);}
 bool next(uint32_t now){
  if(stage!=rest||phase!=done)return false;
  round=std::min(uint32_t(9999),round+1);stage=work;boundary=false;FocusTimer::start(focusTotal,now);return true;
 }
 bool finished(uint32_t now)const{return phase!=off&&boundary&&uint32_t(now-lastBoundary)<10000;}
};
struct DeskCompanion {
 std::string state="unknown";uint32_t updated=0,token=0,greeted=0;bool seen=false,greeting=false,greetingEnabled=true;
 FocusCycle focus;
 const char* presence(uint32_t now)const{return seen&&uint32_t(now-updated)<12000?state.c_str():"unknown";}
 bool away(uint32_t now)const{return std::string(presence(now))=="away";}
 bool welcome(uint32_t now)const{return greeting&&uint32_t(now-greeted)<6000&&std::string(presence(now))=="awake";}
 bool accept(const std::string& next,uint32_t id,uint32_t now){
  bool returned=away(now)&&next=="awake";
  state=next;updated=now;seen=true;
  if(id&&id!=token&&next=="awake"){token=id;if(greetingEnabled){greeting=true;greeted=now;returned=true;}}
  if(next!="awake")greeting=false;
  return returned;
 }
 void configureGreeting(bool enabled){greetingEnabled=enabled;if(!enabled)greeting=false;}
 void dismissWelcome(){greeting=false;}
};
