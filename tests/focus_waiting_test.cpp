#include "focus_waiting.h"
#include "desktop_actions.h"
#include "desk_companion.h"
#include "focus_dial.h"
#include <cassert>
#include <iostream>
struct Canvas {
 void drawPixel(int x,int y,uint16_t){assert(x>=0&&x<320&&y>=40&&y<186);}
};
int main(){
 std::vector<Task> tasks={{"a","running","编译","","","busy","","",""},
  {"b","needs_input","界面","","q1","ask","","",""},
  {"c","needs_input","审查","","q2","ask","","",""}};
 auto target=focusWaitingTarget(tasks,true,2);assert(target.count==2&&target.task->id=="c");
 assert(focusWaitingTarget(tasks,true,0).task->id=="b");
 assert(focusWaitingTarget(tasks,true,99).task->id=="b");
 assert(!focusWaitingTarget(tasks,false,2).task&&focusWaitingTarget(tasks,false,2).count==0);
 FocusWaitingPress press;TouchGesture gesture;DesktopAction action;action.armed=true;
 FocusTimer timer;timer.start(1500,100);FocusPresentation presentation;
 gesture.begin(160,22,1100,false);
 press.begin(target,presentation.controls(1100,true),true,true,160,22);
 assert(!press.captured&&!press.poll(target,true,true,gesture,160,22,2100));
 presentation.reveal(2100); // A first tap only reveals; a separate hold is required.
 auto begin=[&](uint32_t at=2200){press.begin(target,true,true,true,160,22);gesture.begin(160,22,at,false);};
 begin();assert(!press.poll(target,true,true,gesture,160,22,2499));
 assert(press.poll(target,true,true,gesture,160,22,2500)&&gesture.active);
 assert(action.request(press.id,3100));action.queued=false;assert(action.finish(action.serial,"opened",3101));
 assert(!press.poll(target,true,true,gesture,160,22,3102));
 gesture.release(160,22,3200);assert(!press.poll(target,true,true,gesture,160,22,3200));
 assert(timer.phase==FocusTimer::running&&timer.started==100&&timer.remaining(3100)==1497);
 begin();assert(!press.poll(target,false,true,gesture,160,22,2500));assert(!press.poll(target,true,true,gesture,160,22,3200));
 begin();assert(!press.poll(target,true,false,gesture,160,22,2500));assert(!press.poll(target,true,true,gesture,160,22,3200));
 begin();assert(!press.poll(focusWaitingTarget(tasks,false,2),true,true,gesture,160,22,3200));
 begin();tasks[2].waitKey="new question";assert(!press.poll(focusWaitingTarget(tasks,true,2),true,true,gesture,160,22,2500));
 tasks[2].waitKey="q2";assert(!press.poll(target,true,true,gesture,160,22,3200));
 begin();tasks[2].state="running";assert(!press.poll(focusWaitingTarget(tasks,true,2),true,true,gesture,160,22,3200));
 tasks[2].state="needs_input";
 begin();assert(!press.poll(target,true,true,gesture,160,22,6201));
 begin();gesture.move(169,22);assert(!press.poll(target,true,true,gesture,160,22,3300));
 begin();assert(!press.poll(target,true,true,gesture,160,44,2500));assert(!press.poll(target,true,true,gesture,160,22,3300));
 begin();gesture.release(160,22,3100);assert(!press.poll(target,true,true,gesture,160,22,3100));
 begin(UINT32_MAX-999);assert(press.poll(target,true,true,gesture,160,22,0));
 press.reset();assert(!press.captured&&!press.poll(target,true,true,gesture,160,22,0));
 for(bool visible:{false,true})for(bool started:{false,true})for(bool armed:{false,true}){
  press.begin(target,visible,started,armed,160,22);assert(press.captured==(visible&&started&&armed));
 }
 for(int y=0;y<240;y++)for(int x=0;x<320;x++)if(focusWaitingRegion(x,y))assert(FocusLayout::hit(x,y,true)==FocusHit::none);
 Canvas canvas;for(float ratio:{0.f,.25f,.5f,1.f})FocusDial::ring(canvas,ratio,true,false,true);
 // Clearing a waiting task only removes its presentation; elapsed time continues.
 tasks[1].state=tasks[2].state="running";assert(!focusWaitingTarget(tasks,true,2).task);
 assert(timer.remaining(10100)==1490&&timer.phase==FocusTimer::running);
 assert(timer.pause(11100));auto paused=timer.remaining(11100);
 tasks[0].state="needs_input";assert(focusWaitingTarget(tasks,true,0).count==1);
 assert(timer.remaining(21100)==paused&&timer.phase==FocusTimer::paused);
 std::cout<<"Focus waiting: stable target, live gating, deliberate hold, stale cancellation, timer independence and layout bounds passed\n";
}
