#include "focus_dial.h"
#include "desk_companion.h"
#include <cassert>
#include <vector>
struct Canvas{
 std::vector<uint16_t> pixels=std::vector<uint16_t>(320*240);
 int top,bottom;Canvas(int t=0,int b=240):top(t),bottom(b){}
 void drawPixel(int x,int y,uint16_t c){assert(x>=0&&x<320&&y>=top&&y<bottom);pixels[y*320+x]=c;}
};
int main(){
 FocusTimer t;t.start(1500,100);assert(FocusDial::remainingRatio(t.total,t.used(100))==1);
 assert(t.pause(375100));float paused=FocusDial::remainingRatio(t.total,t.used(500100));assert(paused==.75f);
 assert(t.resume(500100));assert(FocusDial::remainingRatio(t.total,t.used(875100))==.5f);
 t.tick(1625100);assert(t.phase==FocusTimer::done&&FocusDial::remainingRatio(t.total,t.used(1625100))==0);
 Canvas half;FocusDial::ring(half,.5f,false,false);assert(half.pixels[120*320+265]>half.pixels[120*320+55]);
 Canvas full,empty;FocusDial::ring(full,1,false,false);FocusDial::ring(empty,0,false,false);
 assert(full.pixels[120*320+55]>empty.pixels[120*320+55]);
 for(bool compact:{false,true})for(float value:{0.f,.001f,.25f,.5f,.75f,1.f}){
  Canvas c(compact?37:10,compact?181:230);FocusDial::ring(c,value,compact,false);
  for(uint32_t seconds:{0u,59u,1111u,1500u,2345u,3599u,5678u,5999u})FocusDial::digits(c,seconds,compact?108:120,compact,false);
 }
}
