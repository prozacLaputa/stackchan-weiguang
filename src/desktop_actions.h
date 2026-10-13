#pragma once
#include <stdint.h>
#include <string>
#include "touch_gesture.h"
#include "focus_ui.h"
#include "notice_state.h"

// 仅真实首页／番茄钟待回应区长按产生请求；无线命令只能取走请求或返回结果。
inline bool waitingRegion(int x,int y){return x>=12&&x<308&&y>=142&&y<236;}
// 阈值到达时消费本次按压，直到下一次按下才重新允许触发。
struct WaitingPress {
 bool captured=false,canceled=false,fired=false;std::string id,key;
 bool (*region)(int,int)=nullptr;
 void reset(){captured=canceled=fired=false;id.clear();key.clear();region=nullptr;}
 void begin(const Task* task,bool eligible,bool (*hit)(int,int),int x,int y){
  reset();if(!eligible||!task||task->id.empty()||task->state!="needs_input"||!hit(x,y))return;
  captured=true;id=task->id;key=task->waitKey;region=hit;
 }
 bool matches(const Task* task,bool eligible)const{
  return captured&&!canceled&&eligible&&task&&task->state=="needs_input"&&task->id==id&&task->waitKey==key;
 }
 void observe(const Task* task,bool eligible){if(captured&&!fired&&!matches(task,eligible))canceled=true;}
 bool poll(const Task* task,bool eligible,const TouchGesture& g,int x,int y,uint32_t now){
  observe(task,eligible);if(!captured||canceled||fired)return false;
  uint32_t held=now-g.startAt;
  if(!g.active||!region(g.startX,g.startY)||!region(x,y)||g.maxTravel>8||g.axis!=Axis::pending||held>4000){canceled=true;return false;}
  if(held<900)return false;
  fired=true;return true;
 }
};
struct DesktopAction {
 uint32_t serial=0,created=0,shown=0;bool queued=false,inFlight=false,armed=false;
 std::string thread,result;
 void reset(){queued=inFlight=armed=false;thread.clear();result.clear();}
 bool request(const std::string& id,uint32_t now){
  if(!armed||id.empty()||inFlight)return false;
  if(++serial==0)++serial;thread=id;created=shown=now;queued=inFlight=true;result="pending";return true;
 }
 bool available(uint32_t now)const{return queued&&inFlight&&uint32_t(now-created)<6000;}
 void tick(uint32_t now){if(inFlight&&uint32_t(now-created)>=6000){queued=inFlight=false;result="timeout";shown=now;}}
 bool finish(uint32_t id,const std::string& value,uint32_t now){
  tick(now);if(!inFlight||queued||serial!=id)return false;
  inFlight=false;result=value;shown=now;return true;
 }
 const char* feedback(uint32_t now)const{
  if(result.empty()||uint32_t(now-shown)>=6000)return "";
  if(result=="pending")return "正在请求 Mac 打开…";
  if(result=="opened")return "已请求 Mac 打开";
  if(result=="stale")return "任务已不再待回应";
  if(result=="locked")return "请先解锁 Mac";
  return "未能打开 · 请在 Mac 查看";
 }
};
