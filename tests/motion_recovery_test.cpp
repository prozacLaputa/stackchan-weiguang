#include "../src/quiet_motion.h"
#include <cassert>
#include <iostream>
FakeServo fake;TestSerial Serial;
void unlockTouch(QuietMotion& m){m.feedback.update(0,false,false,2100);m.feedback.update(0,false,false,2600);}
void fault(QuietMotion& m){
 m.begin();assert(m.requestPet(100));fake.stuck=true;
 for(uint32_t t=140;t<1800;t+=40)m.tick(t,false);
 assert(!m.ready&&m.canRecover());assert(!strcmp(m.lastFault.reason,"pet-follow-error"));
 fake.stuck=false;unlockTouch(m);
}
int main(){
 fake=FakeServo();QuietMotion m;fault(m);auto first=m.lastFault;auto targets=fake.targets.size();
 assert(!strcmp(m.beginRecovery(3000,first.id+1,0,false),"stale-fault"));
 assert(!strcmp(m.beginRecovery(3000,first.id,1,false),"release-required"));
 assert(!strcmp(m.beginRecovery(3000,first.id,-1,false),"head-read"));
 assert(!strcmp(m.beginRecovery(3000,first.id,0,false),"checking"));
 assert(!strcmp(m.beginRecovery(3010,first.id,0,false),"busy"));
 assert(!m.requestPet(3100)&&!m.requestFocus(3100));
 for(uint32_t t=3100;t<=3500;t+=100)m.tickRecovery(t,0,false);
 assert(m.ready&&!m.active()&&!strcmp(m.recoveryResult(),"recovered"));
 assert(fake.targets.size()==targets&&fake.torque==0); // 检查全程没有目标或上力。
 assert(m.lastFault.id==first.id&&m.lastFault.command==first.command&&m.lastFault.load==first.load);
 assert(!m.requestPet(4000)&&m.requestPet(8500)); // 恢复不绕过 5 秒冷却。
 for(uint32_t t=8540;t<11000;t+=40)m.tick(t,false);
 assert(m.ready&&!m.active()&&fake.torque==0);
 for(int failure=0;failure<9;failure++){
  fake=FakeServo();QuietMotion bad;fault(bad);auto id=bad.lastFault.id;targets=fake.targets.size();
  assert(!strcmp(bad.beginRecovery(3000,id,0,false),"checking"));
  if(failure==0)fake.readOk=false;
  if(failure==1)fake.load=550;
  if(failure==2)fake.pos=900;
  if(failure==3)fake.torque=1;
  if(failure==4){bad.tickRecovery(3100,0,false);fake.pos+=3;}
  if(failure==8){bad.cancelRecovery();}
  else bad.tickRecovery(failure==5?4600:3200,failure==6?1:0,failure==7);
  assert(!bad.ready&&!bad.recovering()&&bad.lastFault.id==id&&fake.targets.size()==targets);
  assert(!strcmp(bad.beginRecovery(4000,id,0,false),"cooldown"));
 }
 fake=FakeServo();QuietMotion high;high.begin();assert(high.requestPet(100));fake.load=550;high.tick(240,false);
 assert(!high.canRecover());unlockTouch(high);assert(!strcmp(high.beginRecovery(3000,high.lastFault.id,0,false),"requires-reset"));
 fake=FakeServo();QuietMotion failedRelease;fault(failedRelease);fake.releaseOk=false;
 assert(!strcmp(failedRelease.beginRecovery(3000,failedRelease.lastFault.id,0,false),"release-ack"));
 assert(!fake.powered&&!failedRelease.ready&&!failedRelease.canRecover());
 std::cout<<"Recovery checks: no movement, no automatic retry, preserved fault, cooldown and refusal boundaries passed\n";
}
