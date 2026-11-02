#pragma once
#include <stdint.h>

// 隐藏时的第一次轻点只唤出按钮，不能穿透成暂停或退出。
struct FocusPresentation {
 bool shown=false;uint32_t touched=0;
 void reveal(uint32_t now){shown=true;touched=now;}
 void hide(){shown=false;}
 bool controls(uint32_t now,bool started)const{return !started||(shown&&uint32_t(now-touched)<4500);}
};
inline bool homeFocusEntry(int x,int y){return x>=216&&x<320&&y>=26&&y<66;}

enum class FocusHit { none,back,shorter,normal,longer,primary,stop,motion,custom,add,minus5,minus1,plus1,plus5,save,item0,item1,item2,item3,item4,item5 };
struct FocusLayout {
 static bool entry(int x,int y){return x>=108&&x<204&&y>=28&&y<64;}
 static FocusHit hit(int x,int y,bool started=false,int menu=0){
  if(!started&&menu){
   if(y>=186&&y<234){if(x>=12&&x<108)return FocusHit::back;if(x>=120&&x<308)return menu==1?FocusHit::add:FocusHit::save;}
   if(menu==1&&x>=12&&x<308&&y>=36&&y<174){int col=x>=166?1:0;int row=(y-36)/46;if(x<(col?308:154)&&y<36+row*46+38)return FocusHit(int(FocusHit::item0)+row*2+col);}
   if(menu==2&&y>=126&&y<170&&x>=12&&x<308){int i=(x-12)/76;if(i<4&&x<12+i*76+68)return FocusHit(int(FocusHit::minus5)+i);}
   return FocusHit::none;
  }
  if(!started&&y>=24&&y<64){if(x>=12&&x<104)return FocusHit::shorter;if(x>=114&&x<206)return FocusHit::normal;if(x>=216&&x<308)return FocusHit::longer;}
  if(!started&&y>=138&&y<178){if(x>=12&&x<154)return FocusHit::custom;if(x>=166&&x<308)return FocusHit::motion;}
  if(y>=186&&y<234){if(x>=12&&x<100)return FocusHit::back;if(x>=108&&x<204)return FocusHit::primary;if(x>=212&&x<308)return FocusHit::stop;}
  return FocusHit::none;
 }
};
