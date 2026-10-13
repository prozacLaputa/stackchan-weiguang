#include "../src/quiet_motion.h"
#include <cassert>
#include <iostream>
FakeServo fake;TestSerial Serial;
int main(){
 // 番茄钟到时有独立开关；不借用或打开任务提醒，不排队重放。
 fake=FakeServo();QuietMotion focus;focus.begin();focus.configure(true,false,false,true);
 assert(!focus.request(NoticeKind::done,10)&&!focus.request(NoticeKind::waiting,10));
 assert(!focus.requestFocus(20,true,false)&&!focus.requestFocus(30,false,true));
 assert(fake.targets.empty()&&focus.requestFocus(100));
 focus.tick(850,false);focus.tick(1600,false);assert(!focus.active()&&fake.torque==0);
 assert((fake.targets==std::vector<int>{659,649,659}));assert(!focus.requestFocus(2000));
 focus.configure(true,false,false,false);assert(!focus.requestFocus(25000));
 focus.configure(true,false,false,true);assert(focus.requestFocus(26000));
 focus.configure(true,false,false,false);assert(!focus.active()&&fake.torque==0);
 fake=FakeServo();
 QuietMotion motion;motion.begin();motion.configure(true,true,true);assert(motion.ready&&fake.targets.empty()&&fake.torque==0);
 assert(motion.request(NoticeKind::waiting,100));assert(fake.pos==669&&fake.torque==1);
 motion.tick(850,false);assert(fake.pos==659);motion.tick(1600,false);assert(fake.torque==0);
 assert((fake.targets==std::vector<int>{659,669,659}));
 assert(!motion.request(NoticeKind::done,2000));assert(motion.request(NoticeKind::done,20100));
 assert(fake.pos==649);motion.tick(20850,false);motion.tick(21600,false);assert(fake.pos==659&&fake.torque==0);
 // 两步回位误差不能让下一次动作继续向下漂移。
 fake.pos=657;assert(motion.request(NoticeKind::done,40100));assert(fake.pos==649);
 motion.tick(40850,false);assert(fake.pos==659);motion.tick(41600,false);
 // 读不到位置、写入失败、超出位移范围、负载过高均停止，不重试乱转。
 for(int failure=0;failure<5;failure++){
  fake=FakeServo();QuietMotion m;m.begin();m.configure(true,true,true);assert(m.request(NoticeKind::waiting,100));
  if(failure==0)fake.readOk=false;
  if(failure==1)fake.pos=900;
  if(failure==2)fake.load=700;
  if(failure==3)fake.writeOk=false;
  m.tick(failure==4?2000:850,false);assert(!m.ready&&fake.torque==0);
  auto count=fake.targets.size();assert(!m.request(NoticeKind::done,25000)&&fake.targets.size()==count);
 }
 fake=FakeServo();QuietMotion touched;touched.begin();touched.configure(true,true,true);touched.request(NoticeKind::done,100);
 touched.tick(200,true);assert(fake.torque==0);auto count=fake.targets.size();touched.tick(900,false);assert(fake.targets.size()==count);
 fake=FakeServo();fake.zero=-1;QuietMotion uncalibrated;uncalibrated.begin();uncalibrated.configure(true,true,true);assert(!uncalibrated.ready);
 assert(!uncalibrated.request(NoticeKind::done,100)&&fake.targets.empty());
 fake=FakeServo();fake.torque=1;QuietMotion reboot;reboot.begin();reboot.configure(true,true,true);assert(fake.torque==0&&fake.targets.empty());
 assert(reboot.request(NoticeKind::waiting,100));fake.releaseOk=false;reboot.tick(200,true);
 assert(!fake.powered&&!reboot.ready); // 无法通过总线卸力时必须实际断电。
 // 抚摸时触摸头顶不再取消动作；只做一次完整抬头往返，落点为原休息位置。
 fake=FakeServo();QuietMotion pet;pet.begin();pet.configure(true,true,true);assert(pet.requestPet(100));
 assert(!pet.requestPet(120)&&!pet.request(NoticeKind::waiting,120));
 for(uint32_t t=140;t<=4100;t+=40)pet.tick(t,true,false);
 assert(!pet.active()&&pet.ready&&fake.pos==659&&fake.torque==0);
 int peaks=0,returns=0;bool atPeak=false;
 for(int pos:fake.targets){assert(pos>=659&&pos<=707);if(pos==707&&!atPeak){peaks++;atPeak=true;}if(pos==659&&atPeak){returns++;atPeak=false;}}
 assert(peaks==1&&returns==1);
 assert(!pet.requestPet(4800));assert(pet.requestPet(5100));
 pet.tick(5300,true,true);assert(!pet.active()&&fake.torque==0); // 触屏仍立即停止。
 assert(!pet.request(NoticeKind::done,5400)); // 主动互动后不紧跟自动提醒。
 // 整组动作遇到卡住、负载大、命令失败都卸力，不继续后续点头。
 for(int failure=0;failure<3;failure++){
  fake=FakeServo();QuietMotion m;m.begin();m.configure(true,true,true);assert(m.requestPet(100));
  if(failure==0)fake.stuck=true;
  if(failure==1)fake.load=550;
  if(failure==2)fake.writeOk=false;
  for(uint32_t t=140;t<=1800;t+=40)m.tick(t,true,false);
  assert(!m.ready&&!m.active()&&fake.torque==0);
 }
 fake=FakeServo();fake.pos=820;QuietMotion edge;edge.begin();edge.configure(true,true,true);assert(!edge.requestPet(100)&&fake.targets.empty());
 // 已测得的抬头端 5 步误差可继续；回位误差仍须收敛，不能顺势累积。
 fake=FakeServo();QuietMotion backlash;backlash.begin();backlash.configure(true,true,true);assert(backlash.requestPet(100));
 for(uint32_t t=140;t<=940;t+=40)backlash.tick(t,false);
 fake.pos=702;backlash.tick(1060,false);assert(backlash.ready&&backlash.active());
 for(uint32_t t=1100;t<=1900;t+=40)backlash.tick(t,false);
 fake.pos=665;backlash.tick(2020,false);assert(backlash.ready&&backlash.active());
 backlash.tick(2620,false);assert(!backlash.ready&&!backlash.active()&&fake.torque==0);
 // 冷启动时电源扩展芯片和舵机晚于主控就绪，不应永久丢失主动摸头动作。
 fake=FakeServo();fake.readyAt=650;QuietMotion cold;cold.begin();cold.configure(true,true,true);
 assert(cold.ready&&fake.torque==0&&fake.targets.empty()&&fake.releaseAttempts>1);
 assert(cold.requestPet(100));
 for(uint32_t t=140;t<=4100;t+=40)cold.tick(t,true,false);
 assert(!cold.active()&&cold.ready&&fake.torque==0&&fake.pos==659);
 fake=FakeServo();fake.ioReadyAt=500;QuietMotion slowIO;slowIO.begin();slowIO.configure(true,true,true);
 assert(slowIO.ready&&fake.targets.empty());
 // 即使写回复丢失，必须有独立的扭矩关闭读回，不能仅靠忽略错误。
 fake=FakeServo();fake.missingReleaseReplies=1;QuietMotion lostAck;lostAck.begin();lostAck.configure(true,true,true);
 assert(lostAck.ready&&fake.torque==0&&fake.targets.empty());
 // 持续无响应和无法关闭扭矩均应有上限并实际断电；不能在摸头时绕过。
 for(int failure=0;failure<2;failure++){
  fake=FakeServo();fake.torque=1;if(failure==0)fake.readyAt=100000;else fake.releaseOk=false;
  QuietMotion absent;absent.begin();absent.configure(true,true,true);assert(!absent.ready&&!fake.powered&&fake.clock<4000);
  auto attempts=fake.releaseAttempts;
  assert(!absent.requestPet(100)&&fake.targets.empty()&&fake.releaseAttempts==attempts);
 }
 // 默认只屏幕；通知与摸头独立，开启配置本身不会移动。
 fake=FakeServo();QuietMotion defaults;defaults.begin();auto before=fake.targets.size();
 assert(!defaults.request(NoticeKind::waiting,100)&&!defaults.request(NoticeKind::done,100));
 defaults.configure(false,true,false);assert(fake.targets.size()==before);
 assert(!defaults.requestPet(100)&&!defaults.request(NoticeKind::done,100));
 assert(!defaults.request(NoticeKind::waiting,100,true,false));
 assert(!defaults.request(NoticeKind::waiting,100,false,true));
 assert(fake.targets.size()==before);
 assert(defaults.request(NoticeKind::waiting,100));
 defaults.configure(false,false,true);assert(!defaults.active()&&fake.torque==0);
 before=fake.targets.size();defaults.tick(10000,false);assert(fake.targets.size()==before); // 不补发被丢弃事件。
 assert(!defaults.request(NoticeKind::done,1000)); // 开关不绕过冷却。
 assert(defaults.request(NoticeKind::done,20100));defaults.tick(20850,false);defaults.tick(21600,false);
 assert(!defaults.active()&&fake.torque==0);
 defaults.configure(true,false,false);assert(!defaults.request(NoticeKind::done,40100));
 assert(defaults.requestPet(40100));defaults.configure(false,false,false);
 assert(!defaults.active()&&fake.torque==0);
 std::cout<<"Motor driver: no boot movement, relative nudge, cooldown, touch cancellation and failure stop passed\n";
}
