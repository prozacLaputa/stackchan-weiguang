#include "focus_presets.h"
#include "focus_ui.h"
#include "desk_companion.h"
#include <cassert>
#include <iostream>
int main(){
 FocusPresets p,n;assert(p.defaultMinutes==30&&FocusCycle().focusTotal==1800);
 for(int v:{30,60,120}){assert(!*p.update(p.revision,true,v,n));assert(n.custom.empty()&&n.revision==0);}
 for(int v:{1,37,90,145,180,240}){assert(!*p.update(p.revision,true,v,n));p=n;}
 assert(p.custom.size()==6&&p.revision==6);assert(!*p.update(6,true,37,n)&&n.revision==6);
 assert(std::string(p.update(6,true,40,n))=="full");assert(std::string(p.update(5,false,37,n))=="conflict");
 assert(std::string(p.update(6,false,30,n))=="invalid");
 assert(!*p.update(6,false,37,n));p=n;assert(!*p.update(7,true,45,n));p=n;
 uint32_t words[10];p.encode(words);FocusPresets restored;assert(restored.load(words));assert(restored.csv()==p.csv()&&restored.revision==p.revision);
 for(int i=0;i<10;i++){uint32_t bad[10];std::copy(words,words+10,bad);bad[i]^=0x1234;assert(!restored.load(bad)&&restored.csv()==p.csv());}
 for(int v:{0,-1,241})assert(std::string(p.update(p.revision,true,v,n))=="invalid");
 FocusCycle timer;timer.start(7200,UINT32_MAX-1000);timer.tick(3598999);assert(timer.remaining(3598999)==3600);
 assert(timer.pause(3598999));assert(timer.remaining(4000000)==3600);assert(timer.resume(4000000));timer.tick(7600000);assert(timer.resting()&&timer.remaining(7600000)==300);
 assert(FocusLayout::hit(50,150,false)==FocusHit::custom);
 assert(FocusLayout::hit(50,150,true)==FocusHit::none);
 assert(FocusLayout::hit(50,50,false,1)==FocusHit::item0);
 assert(FocusLayout::hit(170,150,false,1)==FocusHit::item5);
 assert(FocusLayout::hit(160,50,false,1)==FocusHit::none);
 assert(FocusLayout::hit(50,80,false,1)==FocusHit::none);
 assert(FocusLayout::hit(240,210,false,2)==FocusHit::save);
 assert(FocusLayout::hit(50,140,false,2)==FocusHit::minus5);
 assert(FocusLayout::hit(90,140,false,2)==FocusHit::minus1);
 std::cout<<"Preset persistence, limits, conflicts, layout gaps and two-hour rollover passed\n";
}
