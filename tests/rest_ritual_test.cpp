#include "rest_ritual.h"
#include "daily_pet.h"
#include <cassert>
#include <cmath>
#include <set>
#include <iostream>

int main(){
 auto idle=poseFor(FaceMood::idle),sleep=poseFor(FaceMood::rest),shy=poseFor(FaceMood::shy);
 RestRitual r;r.update(false,false,false,idle,100);
 r.update(true,false,false,idle,200);assert(r.phase==RestRitual::fallingAsleep);
 auto first=r.frame(sleep,200);assert(first.eyeHeight==idle.eyeHeight&&first.mouthWidth==idle.mouthWidth);
 auto half=r.frame(sleep,800);assert(half.eyeHeight==4);
 auto yawn=r.frame(sleep,1900);assert(yawn.mouthOpen==7&&yawn.mouthWidth==6);
 r.update(true,false,false,sleep,2000);assert(r.since==200); // Repeated away packets never restart the sequence.
 auto closing=r.frame(sleep,3000);assert(closing.eyeHeight<4&&closing.eyeHeight>1);
 r.update(true,false,false,sleep,3400);assert(!r.active(3400));assert(r.frame(sleep,3400).eyeHeight==1);
 r.update(false,true,false,sleep,3500);assert(r.phase==RestRitual::waking);
 assert(r.frame(shy,4000).eyeHeight==4);assert(r.frame(shy,4550).eyeHeight==1);
 assert(r.frame(shy,5200).cheek==1);
 r.update(false,true,false,shy,5600);assert(!r.active(5600));
 r.update(false,true,false,shy,6000);assert(!r.active(6000)); // Held/repeated head input while awake is ordinary petting.
 r.update(true,false,true,idle,7000);r.update(true,false,false,sleep,7100);assert(!r.active(7100)); // Never replay after a list/notice.
 r.update(false,true,true,sleep,7200);assert(!r.active(7200));
 r.update(true,false,false,idle,8000);r.update(false,false,false,idle,8100);assert(!r.active(8100)); // Task/touch wake is immediate.
 r.update(true,false,false,idle,9000);r.update(true,false,true,sleep,10000);assert(!r.active(10000));
 r.update(false,false,false,idle,11000);r.update(true,false,false,idle,12000);
 auto interrupted=r.frame(sleep,13000);r.update(false,true,false,sleep,13000);
 assert(std::abs(r.frame(shy,13000).mouthOpen-interrupted.mouthOpen)<.001f);
 r.update(false,false,true,idle,13001);assert(!r.active(13001));
 r.update(true,false,false,idle,UINT32_MAX-1000);assert(r.active(1000));
 r.update(true,false,false,sleep,2199);assert(!r.active(2199));

 // Pose bounds and continuity, including the return to the underlying face.
 for(bool waking:{false,true}){
  RestRitual v;if(waking)v.previewWake(sleep,0);else v.update(true,false,false,idle,0);
  auto base=waking?shy:sleep,previous=v.frame(base,0);
  for(uint32_t t=10;t<=v.duration();t+=10){auto p=v.frame(base,t);
   assert(std::isfinite(p.eyeHeight)&&p.eyeHeight>=1&&p.eyeHeight<=10);
   assert(p.mouthOpen>=0&&p.mouthOpen<=7&&p.cheek>=0&&p.cheek<=1);
   assert(std::abs(p.eyeHeight-previous.eyeHeight)<.4f&&std::abs(p.mouthOpen-previous.mouthOpen)<.3f);previous=p;
  }
 }
 for(auto context:{DailyContext::idle,DailyContext::working,DailyContext::affectionate}){
  DailyAnimator d;DailyKind last=DailyKind::none;std::set<DailyKind> observed;
  for(int i=0;i<1000;i++){auto next=d.choose(context);assert(next!=last&&DailyAnimator::allowed(next,context));observed.insert(next);d.last=last=next;}
  assert(observed.size()==(context==DailyContext::idle?4u:context==DailyContext::working?2u:3u));
 }
 DailyAnimator d;d.kind=DailyKind::yawn;d.since=0;d.initialized=true;
 d.tick(100,true,DailyContext::working);assert(d.kind==DailyKind::none); // New work immediately stops a yawn.
 d.kind=DailyKind::look;d.since=100;d.situation=DailyContext::working;
 for(uint32_t t=100;t<3300;t+=20)assert(std::abs(d.frame(idle,t).x)<=3.001f);
 d.tick(4000,false,DailyContext::idle);assert(d.kind==DailyKind::none);
 std::cout<<"Natural cat: sleep/wake transitions, preemption, no replay, wrap, pose continuity and contextual nonrepeating choices passed\n";
}
