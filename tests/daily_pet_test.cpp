#include "daily_pet.h"
#include <cassert>
#include <cmath>
#include <iostream>
int main(){
 CatPetting c;c.update(1,false,100);assert(!c.content(100));
 c.update(1,false,999);assert(!c.content(999));
 c.update(1,false,1000);assert(c.content(1000));
 c.update(0,false,1050);assert(c.content(3599));
 c.update(0,false,3600);assert(!c.content(3600));
 c.update(1,false,4000);c.update(1,false,4200);c.update(0,false,4250);
 c.update(1,false,4300);c.update(1,false,4900);assert(c.content(4900));
 c.update(0,false,5000);c.update(1,false,5400);assert(!c.content(5400));
 c.update(1,false,6400);assert(c.content(6400));
 c.update(1,true,6401);assert(!c.content(6401));
 c.update(1,false,6500);assert(!c.content(6500));c.update(-1,false,7500);assert(!c.content(7500));
 c.update(1,false,UINT32_MAX-400);c.update(1,false,600);assert(c.content(600));
 c.preview(2000);assert(c.content(2000));c.update(0,false,4599);assert(c.content(4599));
 c.update(0,false,4600);assert(!c.content(4600));
 CatPetting memory;memory.update(1,false,100);memory.update(0,false,150);assert(!memory.affectionate(150));
 memory.update(1,false,1000);memory.update(1,false,1120);assert(memory.affectionate(1120)&&memory.strokes==1);
 memory.update(1,false,1500);assert(memory.strokes==1);memory.update(0,false,1550);
 memory.update(1,false,1900);memory.update(1,false,2020);assert(memory.strokes==2&&memory.content(2020));
 memory.update(0,false,2070);assert(memory.softBlink(6020));assert(!memory.softBlink(8020));
 assert(memory.softBlink(26020));assert(!memory.affectionate(122020));
 memory.update(1,true,122021);assert(!memory.content(122021));
 auto content=poseFor(FaceMood::content);assert(content.eyeHeight<2&&content.mouthWidth<20&&content.cheek>0);
 assert(!knownExpression("content")); // 触摸专属表情不能由聊天协议冒充。
 DailyAnimator d;d.tick(1000,true);d.tick(45999,true);assert(d.kind==DailyKind::none);
 d.tick(46000,true);assert(d.kind!=DailyKind::none);d.kind=DailyKind::look;
 auto base=poseFor(FaceMood::idle);auto f=d.frame(base,46000);assert(std::abs(f.x)<.001f);
 bool moved=false;
 for(uint32_t t=46000;t<=49200;t+=20){f=d.frame(base,t);assert(std::abs(f.x)<=7.001f&&std::abs(f.y)<=1.001f);moved|=std::abs(f.x)>2;}
 assert(moved);d.tick(49200,true);assert(d.kind==DailyKind::none&&d.waitMs>=45000&&d.waitMs<=90000);
 uint32_t next=49200+d.waitMs;d.tick(next,true);assert(d.kind!=DailyKind::none);d.kind=DailyKind::grin;
 f=d.frame(base,next+1300);assert(f.pose.eyeHeight==2&&f.pose.mouthCurve==6);
 // 任意高优先级状态立即取消，取消期间不积累待播动画。
 d.tick(next+1301,false);assert(d.kind==DailyKind::none);
 d.tick(next+300000,false);d.tick(next+300001,true);assert(d.kind==DailyKind::none);
 d.tick(next+300000+d.waitMs,true);assert(d.kind!=DailyKind::none);d.kind=DailyKind::yawn;
 f=d.frame(base,d.since+1900);assert(f.pose.mouthOpen==10&&f.pose.eyeHeight==1);
 d.cancel(UINT32_MAX-1000);d.waitMs=35000;d.tick(34000,true);assert(d.kind!=DailyKind::none);
 std::cout<<"Cat petting duration/release/screen/sensor/wrap and daily priority/cadence passed\n";
}
