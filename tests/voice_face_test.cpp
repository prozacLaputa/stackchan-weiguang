#include "voice_face.h"
#include "cat_skin.h"
#include <cassert>
#include <iostream>
struct Canvas {
 void point(int x,int y){assert(x>=12&&x<308&&y>=32&&y<166);}
 void fillCircle(int x,int y,int r,uint16_t){point(x-r,y-r);point(x+r,y+r);}
 void drawEllipse(int x,int y,int rx,int ry,uint16_t){point(x-rx,y-ry);point(x+rx,y+ry);}
 uint16_t color565(int,int,int){return 0xffff;}
};
int main(){
 VoiceFace voice;auto base=poseFor(FaceMood::rest);Canvas canvas;
 assert(!voice.active(0));assert(!voice.accept(4,0));
 assert(voice.accept(3,100));assert(voice.active(699)&&!voice.active(700));
 auto talking=voice.frame(base,165,true);
 assert(talking.mouthOpen>1.5f&&talking.eyeHeight>base.eyeHeight);
 assert(voice.frame(base,200,false).mouthOpen==base.mouthOpen); // touch expression wins
 voice.accept(3,300);voice.frame(base,365,true);voice.accept(-1,400);
 assert(voice.frame(base,401,true).mouthOpen==base.mouthOpen); // stop is immediate
 voice.accept(3,500);voice.frame(base,565,true);
 assert(voice.frame(base,1100,true).eyeHeight==base.eyeHeight); // app/transport disappearance
 voice.accept(1,UINT32_MAX-200);assert(voice.active(200)&&!voice.active(399));
 voice.clear();assert(!voice.active(0));
 for(int level=0;level<=3;level++)for(uint32_t now=0;now<1500;now+=65){
  voice.accept(level,now);auto p=voice.frame(base,now,true);
  assert(p.mouthOpen>=0&&p.mouthOpen<=7.21f);
  drawCatSkin(canvas,p,160,99,1,2,now,0xffff);
 }
 std::cout<<"Voice face: expiry, stop, touch priority, rollover and cat bounds passed\n";
}
