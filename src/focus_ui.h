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

enum class FocusHit { none,back,shorter,normal,longer,primary,stop,motion };
struct FocusLayout {
 static bool entry(int x,int y){return x>=108&&x<204&&y>=28&&y<64;}
 static FocusHit hit(int x,int y,bool started=false){
  if(!started&&y>=24&&y<64){if(x>=12&&x<104)return FocusHit::shorter;if(x>=114&&x<206)return FocusHit::normal;if(x>=216&&x<308)return FocusHit::longer;}
  if(!started&&x>=12&&x<308&&y>=146&&y<178)return FocusHit::motion;
  if(y>=186&&y<234){if(x>=12&&x<100)return FocusHit::back;if(x>=108&&x<204)return FocusHit::primary;if(x>=212&&x<308)return FocusHit::stop;}
  return FocusHit::none;
 }
};
