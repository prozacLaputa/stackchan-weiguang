#include "../src/quiet_motion.h"
#include <cassert>
#include <cstring>
#include <iostream>
FakeServo fake;TestSerial Serial;
bool eq(const char* a,const char* b){return std::strcmp(a,b)==0;}
void touch(QuietMotion& m,uint32_t t){
 m.feedback.update(0,false,false,t-600);m.feedback.update(0,false,false,t-200);
 assert(!m.feedback.update(1,false,false,t));
 assert(m.feedback.update(1,false,false,t+120));
}
int main(){
 // 与旧入口逐次比对，观察层不改变去抖、抬手、触屏与已有动作的门槛。
 PetContact old;PetFeedback observed;uint32_t random=7;
 for(uint32_t t=0;t<30000;t+=10){
  random=random*1664525+1013904223;int raw=int((random>>16)%30);raw=raw<12?0:raw<28?1:-1;
  bool screen=(random%47)==0,active=(random%83)==0,event=false;
  if(screen||active||raw<0)old.cancel(t);else event=old.update(raw>0,t);
  assert(observed.update(raw,screen,active,t)==event);
 }
 QuietMotion m;m.begin();touch(m,1000);assert(m.feedback.event==1);
 assert(m.requestPet(1120,true));assert(eq(m.feedback.result,"moving"));
 for(uint32_t t=1160;t<=3200;t+=40){m.feedback.update(1,false,m.active(),t);m.tick(t,true,false);}
 assert(eq(m.feedback.result,"completed")&&fake.torque==0&&fake.pos==659);
 auto count=fake.targets.size();assert(eq(m.petState(3200),"cooldown"));assert(m.cooldown(3200)==2920);
 touch(m,4000);assert(!m.requestPet(4120,true));
 assert(eq(m.feedback.result,"skipped")&&eq(m.feedback.reason,"cooldown")&&fake.targets.size()==count);
 m.feedback.update(0,false,false,6200);m.feedback.update(0,false,false,6600);
 assert(eq(m.petState(6600),"ready"));
 // 查询本身绝不能向电机下命令。
 for(int i=0;i<20;i++){m.petState(7000);m.faultReason();m.cooldown(7000);m.feedback.age(7000);}
 assert(fake.targets.size()==count);
 PetFeedback shortTouch;shortTouch.update(0,false,false,0);shortTouch.update(0,false,false,400);
 shortTouch.update(1,false,false,500);shortTouch.update(0,false,false,550);
 assert(shortTouch.event==1&&eq(shortTouch.reason,"too-short"));
 shortTouch.update(1,true,false,800);assert(eq(shortTouch.reason,"screen-touch"));
 shortTouch.update(0,false,false,900);shortTouch.update(1,false,false,950);
 assert(eq(shortTouch.reason,"release-required"));
 // 新触摸被正在执行的旧动作挡住时，旧动作完成不能覆盖新触摸原因。
 fake=FakeServo();QuietMotion busy;busy.begin();touch(busy,1000);assert(busy.requestPet(1120,true));
 busy.feedback.update(0,false,true,1160);busy.feedback.update(1,false,true,1200);
 assert(busy.feedback.event==2&&eq(busy.feedback.reason,"busy"));
 for(uint32_t t=1160;t<=3200;t+=40)busy.tick(t,true,false);
 assert(eq(busy.feedback.result,"skipped")&&eq(busy.feedback.reason,"busy"));
 // 真驱动分支的故障记录：负载异常应卸力、停用；以后摸头不重试。
 fake=FakeServo();QuietMotion fault;fault.begin();touch(fault,1000);assert(fault.requestPet(1120,true));
 fake.load=550;fault.tick(1240,true);assert(!fault.ready&&fake.torque==0);
 assert(eq(fault.feedback.result,"failed")&&eq(fault.feedback.reason,"load-high"));
 assert(eq(fault.petState(1400),"unavailable")&&eq(fault.faultReason(),"load-high"));
 count=fake.targets.size();touch(fault,8000);assert(!fault.requestPet(8120,true));
 assert(fake.targets.size()==count&&eq(fault.feedback.reason,"load-high"));
 fake=FakeServo();QuietMotion screen;screen.begin();touch(screen,1000);assert(screen.requestPet(1120,true));
 screen.tick(1240,true,true);assert(screen.ready&&!screen.active()&&fake.torque==0);
 assert(eq(screen.feedback.result,"stopped")&&eq(screen.feedback.reason,"screen-touch"));
 fake=FakeServo();QuietMotion off;off.begin();off.configure(false,false,false);touch(off,1000);
 assert(!off.requestPet(1120,true)&&eq(off.feedback.reason,"preference")&&fake.targets.empty());
 fake=FakeServo();fake.pos=820;QuietMotion edge;edge.begin();touch(edge,1000);
 assert(!edge.requestPet(1120,true)&&eq(edge.feedback.reason,"position-limit")&&edge.ready&&fake.targets.empty());
 fake=FakeServo();fake.zero=-1;QuietMotion cal;cal.begin();assert(eq(cal.faultReason(),"calibration"));
 // 时间回绕不会让冷却或记录变成负数。
 fake=FakeServo();QuietMotion wrap;wrap.begin();assert(wrap.requestPet(UINT32_MAX-100));
 assert(wrap.cooldown(100)==4799);
 std::cout<<"Pet feedback: unchanged contact decisions, actual driver reasons, cooldown, last-event ownership and no query motion passed\n";
}
