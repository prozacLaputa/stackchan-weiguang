#include <cassert>
#include "desk_extras.h"
int main(){
 DeskExtras d;
 d.setRecap(1,false,{{"id","wait","title"}},100);
 assert(d.recapLive(100));assert(!d.recapLive(8100));
 d.page=1;d.setRecap(1,true,{{"id","wait","title"}},200);assert(d.page==1);
 d.setRecap(2,true,{},300);assert(d.page==0);
 d.musicPresent=true;d.musicAt=100;d.elapsed=50;d.duration=60;d.playing=false;
 assert(d.progress(3000)==50);d.playing=true;assert(d.progress(3100)==53);assert(!d.musicLive(9000));
 assert(!d.request("next","key",100));d.armed=true;
 assert(d.request("next","key",100));assert(!d.request("next","key",200));
 d.tick(6200);assert(!d.inFlight&&!d.pending);
 d.clear();assert(!d.armed&&!d.musicLive(100));
 assert(DeskExtras::entry(20,40)==1&&DeskExtras::entry(140,40)==2&&DeskExtras::entry(240,40)==0);
 assert(DeskExtras::musicButton(30,210)==1&&DeskExtras::musicButton(150,210)==2&&DeskExtras::musicButton(270,210)==3);
}
