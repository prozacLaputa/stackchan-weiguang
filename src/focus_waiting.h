#pragma once
#include "desktop_actions.h"

struct FocusWaitingTarget { const Task* task=nullptr; int count=0; };
inline FocusWaitingTarget focusWaitingTarget(const std::vector<Task>& tasks,bool live,int current){
 FocusWaitingTarget result;if(!live)return result;
 for(int i=0;i<int(tasks.size());i++)if(tasks[i].state=="needs_input"&&!tasks[i].id.empty()){
  result.count++;
  if(!result.task||i==current)result.task=&tasks[i];
 }
 return result;
}
inline bool focusWaitingRegion(int x,int y){return x>=12&&x<308&&y>=0&&y<44;}
// Capture the exact question visible at touch-down. A changed task/question cancels the hold.
struct FocusWaitingPress : WaitingPress {
 void begin(const FocusWaitingTarget& target,bool visible,bool started,bool armed,int x,int y){
  WaitingPress::begin(target.task,visible&&started&&armed,focusWaitingRegion,x,y);
 }
 bool matches(const FocusWaitingTarget& target,bool armed)const{
  return WaitingPress::matches(target.task,armed);
 }
 bool poll(const FocusWaitingTarget& target,bool armed,bool samePhase,const TouchGesture& g,int x,int y,uint32_t now){
  return WaitingPress::poll(target.task,armed&&samePhase,g,x,y,now);
 }
};
