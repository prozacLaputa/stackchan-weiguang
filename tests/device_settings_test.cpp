#include "../src/device_settings.h"
#include "../src/standby_state.h"
#include "../src/touch_gesture.h"
#include <cassert>
#include <iostream>
int main(){
 DeviceSettings s;assert(s.brightness()==70&&s.idleMs()==180000&&s.petMotion&&!s.waitMotion&&!s.doneMotion);
 for(int l=0;l<4;l++)for(int r=0;r<5;r++)for(int p=0;p<2;p++)for(int w=0;w<2;w++)for(int d=0;d<2;d++){
  assert(s.set(l,r,p,w,d));DeviceSettings copy;assert(copy.load(s.packed()));assert(copy.packed()==s.packed());
  assert(copy.load(0x57010000u|l|(r<<4)|(p<<8)));
  assert(copy.light==l&&copy.rest==r&&copy.petMotion==bool(p)&&!copy.waitMotion&&!copy.doneMotion);
 }
 auto old=s.packed();for(uint32_t bad:{0u,0xffffffffu,0x57010004u,0x57010050u,0x57010200u,0x57020800u,0x57020004u,0x57030004u}){assert(!s.load(bad));assert(s.packed()==old);}
 assert(!s.set(2,2,0,2,0)&&s.packed()==old);
 assert(!s.set(-1,1,1)&&!s.set(1,5,1)&&!s.set(1,1,2));assert(s.packed()==old);
 s.set(0,0,0);assert(!SettingsLayout::change(s,SettingHit::lightDown));assert(!SettingsLayout::change(s,SettingHit::restDown));
 assert(SettingsLayout::change(s,SettingsLayout::hit(286,95)));assert(s.light==1);
 assert(SettingsLayout::change(s,SettingsLayout::hit(286,145)));assert(s.rest==1);
 assert(SettingsLayout::change(s,SettingsLayout::hit(200,192))&&s.petMotion);
 assert(SettingsLayout::entry(240,40)&&!SettingsLayout::entry(204,40));
 assert(SettingsLayout::hit(250,40)==SettingHit::section);
 s.waitMotion=false;s.doneMotion=false;
 assert(SettingsLayout::change(s,SettingsLayout::hit(236,95,true))&&s.waitMotion&&!s.doneMotion);
 assert(SettingsLayout::change(s,SettingsLayout::hit(236,145,true))&&s.waitMotion&&s.doneMotion);
 assert(SettingsLayout::hit(236,192,true)==SettingHit::none);
 assert(SettingsLayout::hit(160,120)==SettingHit::none&&SettingsLayout::hit(236,145)==SettingHit::none);
 TouchGesture gesture;gesture.begin(286,95,0,false);gesture.move(286,116);assert(!gesture.release(286,116,50).tap);
 gesture.begin(286,95,0,false);assert(!gesture.release(286,95,700).tap);
 StandbyState standby;std::vector<Task> idle={{"one","done","test","","","idle"}};
 standby.configure(110,60000,0);standby.begin(0);assert(standby.brightness(0)==110);
 standby.tick(59999,true,idle,false);assert(!standby.resting());standby.tick(60000,true,idle,false);assert(standby.resting());
 standby.configure(40,0,60100);standby.tick(10000000,true,idle,false);assert(!standby.resting()&&standby.brightness(10000000)==40);
 standby.configure(160,300000,10000001);standby.tick(10300001,true,idle,false);assert(standby.resting());
 std::cout<<"Settings: persistence validation, bounds, tap targets, swipe rejection, brightness and idle control passed\n";
}
