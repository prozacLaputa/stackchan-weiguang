#include "device_settings.h"
#include "remote_settings.h"
#include "desk_companion.h"
#include "daily_pet.h"
#include <cassert>
#include <iostream>
int main(){
 DeviceSettings s;
 for(int l=0;l<4;l++)for(int r=0;r<5;r++)for(int p=0;p<2;p++)for(int w=0;w<2;w++)for(int d=0;d<2;d++){
  uint32_t legacy=0x57020000u|l|(r<<4)|(p<<8)|(w<<9)|(d<<10);
  s.daily=2;s.awayRest=s.greeting=s.affection=false;
  assert(s.load(legacy));assert(s.light==l&&s.rest==r&&s.petMotion==bool(p)&&s.waitMotion==bool(w)&&s.doneMotion==bool(d));
  assert(s.daily==1&&s.awayRest&&s.greeting&&s.affection);
  for(int f=0;f<3;f++)for(int a=0;a<2;a++)for(int g=0;g<2;g++)for(int c=0;c<2;c++){
   assert(s.setAll(l,r,p,w,d,f,a,g,c));DeviceSettings copy;assert(copy.load(s.packed()));assert(copy.packed()==s.packed());
  }
 }
 auto before=s.packed();
 for(auto bad:{0x57031800u,0x57030050u,0x57030004u,0x57030080u})assert(!s.load(bad)&&s.packed()==before);
 assert(!patchDeviceSettings(s,"3","-","-","-","-","3","0","0","0")&&s.packed()==before);
 assert(patchDeviceSettings(s,"-","-","-","-","-","1","1","0","1"));
 assert(s.daily==1&&s.awayRest&&!s.greeting&&s.affection);
 auto copy=s;assert(patchDeviceSettings(s,"0","-","-"));assert(s.daily==copy.daily&&s.greeting==copy.greeting&&s.affection==copy.affection);
 s.petMotion=true;s.waitMotion=s.doneMotion=false;
 assert(SettingsLayout::hit(236,95,2)==SettingHit::daily);assert(SettingsLayout::hit(236,145,2)==SettingHit::away);assert(SettingsLayout::hit(236,192,2)==SettingHit::greeting);
 assert(SettingsLayout::hit(236,95,3)==SettingHit::affection);assert(SettingsLayout::hit(236,145,3)==SettingHit::none);
 for(int page=0;page<5;page++){assert(SettingsLayout::hit(30,40,page)==SettingHit::back);assert(SettingsLayout::hit(220,40,page)==SettingHit::section);assert(SettingsLayout::nextPage(page)==(page+1)%5);}
 for(int i=0;i<3;i++)assert(SettingsLayout::change(s,SettingHit::daily));assert(s.daily==1);
 assert(s.petMotion&&!s.waitMotion&&!s.doneMotion);
 DeskCompanion desk;desk.accept("away",0,100);desk.configureGreeting(false);desk.accept("awake",42,1000);assert(!desk.welcome(1000));
 desk.configureGreeting(true);desk.accept("awake",42,1100);assert(!desk.welcome(1100)); // Re-enabling never replays consumed token.
 desk.accept("away",0,2000);desk.accept("awake",43,3000);assert(desk.welcome(3000));desk.configureGreeting(false);assert(!desk.welcome(3001));
 CatPetting cat;cat.update(1,false,100);cat.update(1,false,1000);cat.update(0,false,1100);assert(cat.content(1200)&&cat.softBlink(5000));
 cat.setAffection(false);assert(!cat.softBlink(5001));cat.setAffection(true);assert(!cat.softBlink(5002));
 cat.setAffection(false);cat.update(1,false,10000);cat.update(1,false,10900);assert(cat.content(10900));cat.update(0,false,11000);assert(!cat.softBlink(14900));
 // Continuous petting and a quick second stroke still give direct feedback with memory off.
 cat.update(1,false,11400);cat.update(1,false,11520);assert(cat.content(11520)&&!cat.affectionate(11520));
 for(int level=0;level<3;level++){
  DailyAnimator d;d.configure(level,1000);d.tick(1000,true);
  uint32_t min=level==0?180000:level==2?20000:45000,max=level==0?300000:level==2?40000:90000;
  assert(d.waitMs==min);d.tick(1000+min-1,true);assert(d.kind==DailyKind::none);d.tick(1000+min,true);assert(d.kind!=DailyKind::none);
  uint32_t now=1000+min;
  for(int cycle=0;cycle<100;cycle++){
   now+=DailyAnimator::duration(d.kind);d.tick(now,true);assert(d.kind==DailyKind::none&&d.waitMs>=min&&d.waitMs<=max);
   now+=d.waitMs;d.tick(now,true);assert(d.kind!=DailyKind::none);
  }
  d.tick(now+1,false);assert(d.kind==DailyKind::none);d.configure((level+1)%3,now+2);assert(d.kind==DailyKind::none);
 }
 std::cout<<"Companion settings: legacy migration, atomic save, UI targets, independent motor flags and no stale replay passed\n";
}
