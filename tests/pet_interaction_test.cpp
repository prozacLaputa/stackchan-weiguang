#include "../src/pet_interaction.h"
#include "../src/motion_plan.h"
#include <cassert>
#include <iostream>
int main(){
 PetContact c;
 for(uint32_t t=0;t<2000;t+=50)assert(!c.update(true,t)); // 开机已有接触，不擅自动。
 assert(!c.update(false,2000));assert(!c.update(false,2400));
 assert(!c.update(true,2450));assert(!c.update(true,2500));assert(c.update(true,2570));
 for(uint32_t t=2600;t<8000;t+=50)assert(!c.update(true,t));
 assert(!c.update(false,8050));assert(!c.update(true,8100));assert(!c.update(true,8300)); // 短松手不重播。
 c.update(false,8400);c.update(false,8800);c.update(true,8850);assert(c.update(true,9000));
 c.cancel(9010);assert(!c.update(true,9200)&&!c.update(true,9500));
 PetContact wrap;wrap.update(false,UINT32_MAX-500);wrap.update(false,UINT32_MAX-100);
 wrap.update(true,UINT32_MAX-50);assert(wrap.update(true,100));
 int prev=659;for(int t=0;t<=900;t+=10){int pos=petTrajectory(659,707,t);assert(pos>=prev&&pos<=707);prev=pos;}
 prev=707;for(int t=0;t<=900;t+=10){int pos=petTrajectory(707,659,t);assert(pos<=prev&&pos>=659);prev=pos;}
 assert(petTrajectory(659,707,400)==683&&petTrajectory(659,707,800)==707);
 NudgePlan p;
 for(int zero=0;zero<=1000;zero+=7)for(int pos=0;pos<=1000;pos++)if(p.preparePet(zero,pos,20,1003)){
  assert(p.target-p.origin==48&&p.target<=zero+272&&p.origin>=zero+16);
  assert(p.contains(p.target)&&!p.contains(p.target+5)&&!p.contains(p.origin-5));
 }
 std::cout<<"Head pet contact debounce, rearm, easing and limits passed\n";
}
