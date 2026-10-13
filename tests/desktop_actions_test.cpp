#include "desktop_actions.h"
#include "desk_companion.h"
#include "device_settings.h"
#include <cassert>
#include <iostream>
int main(){
 TouchGesture g;WaitingPress press;
 Task task{"id","needs_input","待处理","","question-1","ask","","",""};
 auto begin=[&](uint32_t at=100){g.begin(100,183,at,false);press.begin(&task,true,waitingRegion,100,183);};
 begin();assert(!press.poll(&task,true,g,100,183,999));
 assert(press.poll(&task,true,g,100,183,1000)&&g.active&&press.fired); // Still held at threshold.
 DesktopAction dispatched;dispatched.armed=true;assert(dispatched.request(press.id,1000));
 dispatched.queued=false;assert(dispatched.finish(dispatched.serial,"opened",1001));
 assert(!press.poll(&task,true,g,100,183,1002)); // ACK does not rearm this finger.
 assert(!press.poll(&task,true,g,100,183,9000)); // Nor does feedback expiry.
 auto r=g.release(100,183,9001);assert(!r.tap&&!press.poll(&task,true,g,100,183,9001));
 assert(dispatched.serial==1);
 begin(10000);assert(press.poll(&task,true,g,100,183,10900)); // Next touch can open again.
 begin();g.release(100,183,999);assert(!press.poll(&task,true,g,100,183,1000));
 begin();g.release(100,183,1100);assert(!press.poll(&task,true,g,100,183,1100)); // Release is never a trigger.
 begin();g.move(109,183);assert(!press.poll(&task,true,g,100,183,1000));
 begin();assert(!press.poll(&task,true,g,100,239,500));assert(!press.poll(&task,true,g,100,183,1000));
 begin();assert(!press.poll(&task,true,g,100,183,4101));
 begin();press.observe(&task,false);press.observe(&task,true);assert(!press.poll(&task,true,g,100,183,1000));
 begin();task.waitKey="question-2";press.observe(&task,true);task.waitKey="question-1";assert(!press.poll(&task,true,g,100,183,1000));
 begin();Task other=task;other.id="other";assert(!press.poll(&other,true,g,100,183,1000));
 begin();task.state="running";assert(!press.poll(&task,true,g,100,183,1000));task.state="needs_input";
 begin(UINT32_MAX-499);assert(press.poll(&task,true,g,100,183,400));
 begin();assert(g.release(100,183,200).tap); // Normal tap keeps list navigation.
 for(bool ready:{false,true}){press.begin(&task,ready,waitingRegion,100,183);assert(press.captured==ready);}
 press.begin(&task,true,waitingRegion,100,100);assert(!press.captured);
 press.begin(nullptr,true,waitingRegion,100,183);assert(!press.captured);
 DesktopAction a;assert(!a.request("id",100));a.armed=true;assert(a.request("id",100));
 assert(!a.request("another",200)&&a.thread=="id");assert(a.available(1000));assert(!a.finish(a.serial,"opened",1000));
 a.queued=false;assert(!a.finish(a.serial+1,"opened",1000));assert(a.finish(a.serial,"opened",1000));assert(!a.finish(a.serial,"opened",1100));
 assert(std::string(a.feedback(1001))=="已请求 Mac 打开");
 a.request("id",2000);a.tick(8000);assert(!a.available(8000)&&!a.inFlight&&a.result=="timeout");
 a.reset();assert(!a.armed&&!a.available(9000));
 // Three header targets never overlap; rows remain browse-only.
 ListLayout list{320,240};
 for(int x=12;x<308;x++){
  int hits=int(list.hit(x,40)==Hit::back)+int(FocusLayout::entry(x,40))+int(SettingsLayout::entry(x,40));
  assert(hits<=1);assert(list.hit(x,120)==Hit::none);
 }
 assert(FocusLayout::hit(150,200)==FocusHit::primary&&FocusLayout::hit(250,200)==FocusHit::stop);
 FocusTimer f;f.start(1500,100);assert(f.pause(60550));auto left=f.remaining(60550);
 assert(left==1440&&f.remaining(1000000)==left);assert(!f.pause(1000000));
 assert(f.resume(1000000)&&!f.resume(1000001));assert(f.remaining(1000550)==1439);
 f.tick(2439550);assert(f.phase==FocusTimer::done&&f.finished(2439550));
 f.start(60,UINT32_MAX-999);assert(f.pause(0));assert(f.remaining(999999)==59);
 assert(f.resume(UINT32_MAX-99));f.tick(58900);assert(f.phase==FocusTimer::done);
 f.start(60,0);assert(!f.pause(60000)&&f.phase==FocusTimer::done);f.stop();assert(!f.resume(61000));
 std::cout<<"Long press, disjoint hit regions, one-shot dispatch, stale reset and pause/resume timing passed\n";
}
