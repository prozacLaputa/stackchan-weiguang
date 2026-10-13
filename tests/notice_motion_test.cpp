#include "../src/ui_state.h"
#include "../src/motion_plan.h"
#include "../src/device_settings.h"
#include <cassert>
#include <iostream>

int main(){
 UiState u;std::vector<Task> ts={{"a","running","主任务","",""},{"b","running","另一个任务","",""},{"c","done","旧任务","old",""}};
 u.update(ts,100,false);assert(u.noticeSerial==0&&!u.celebrating);
 u.open(110);
 ts[1].state="done";ts[1].doneKey="turn-b";
 u.update(ts,200);assert(u.noticeSerial==1&&u.celebrating&&u.currentIndex==1&&u.details);
 u.update(ts,300);assert(u.noticeSerial==1);u.tick(6200);assert(!u.celebrating&&u.currentIndex==0);
 // 同一状态的新轮次仍能识别；重复快照与中断不冒充完成。
 ts[1].doneKey="turn-b2";ts[2].doneKey="turn-c2";u.update(ts,7000);
 assert(u.latestNotice.completed==2&&u.completedCount==2&&u.noticeSerial==2);
 ts[0].state="interrupted";u.update(ts,7100);assert(u.noticeSerial==2);
 ts[0].state="needs_input";ts[0].waitKey="question1";u.update(ts,7200);
 assert(u.noticeSerial==3&&u.latestNotice.kind==NoticeKind::waiting&&!u.celebrating&&u.currentIndex==0);
 ts[0].waitKey="";ts[0].state="running";u.update(ts,7300);
 ts[0].waitKey="question1";ts[0].state="needs_input";u.update(ts,7400);assert(u.noticeSerial==3);
 ts[0].waitKey="question2";u.update(ts,7500,false);assert(u.noticeSerial==3);
 u.update(ts,7600);assert(u.noticeSerial==3); // 重连只建立新基线。
 auto serial=u.noticeSerial;u.update({},7700);u.update(ts,7800);assert(u.noticeSerial==serial);
 ts[0].state="running";ts[0].waitKey="";ts[1].doneKey="turn-b3";u.update(ts,8000);assert(u.celebrating);
 ts.erase(ts.begin()+1);u.update(ts,8100);assert(!u.celebrating); // 不把被移走任务的完成笑脸套到别的任务。
 // 扫描所有合理零位和起点：仅允许安全范围内的 10 步小动作。
 NudgePlan p;
 for(int zero=-1;zero<=1001;zero+=7)for(int pos=-1;pos<=1024;pos++)for(bool waiting:{false,true}){
  if(p.prepare(zero,pos,20,1003,waiting)){
   assert(p.origin>=zero+16&&p.target>=zero+16&&p.target<=zero+272&&p.target<=1000);
   assert(std::abs(p.target-p.origin)==10&&p.contains(p.target)&&p.contains(p.origin));
   assert(!p.contains(p.origin+15)&&!p.contains(p.origin-15));
  }
 }
 assert(!p.prepare(-1,659,20,1003,true));assert(!p.prepare(573,-1,20,1003,true));
 assert(!p.prepare(573,659,0,0,true));assert(p.prepare(573,659,20,1003,true)&&p.target==669);
 assert(p.prepare(573,659,20,1003,false)&&p.target==649);
 MotionGate gate;assert(gate.allows(100));gate.record(UINT32_MAX-10000);
 assert(!gate.allows(1000)&&gate.allows(10000));
 DeviceSettings settings;NoticeEvents events;events.kind=NoticeKind::waiting;events.completed=2;
 assert(settings.notificationMotion(events)==NoticeKind::none);
 settings.doneMotion=true;assert(settings.notificationMotion(events)==NoticeKind::done);
 settings.waitMotion=true;assert(settings.notificationMotion(events)==NoticeKind::waiting);
 events.completed=0;settings.waitMotion=false;assert(settings.notificationMotion(events)==NoticeKind::none);
 events.kind=NoticeKind::done;events.completed=1;assert(settings.notificationMotion(events)==NoticeKind::done);
 // 新开启动作开关不改变事件去重：旧快照和重连都不会重新产生 noticeSerial。
 auto previous=u.noticeSerial;settings.waitMotion=true;u.update(ts,42000,false);u.update(ts,43000,true);
 assert(u.noticeSerial==previous);
 std::cout<<"Notification dedupe, all-task completion, reconnect and bounded-motion tests passed\n";
}
