#include "cat_skin.h"
#include "device_settings.h"
#include "remote_settings.h"
#include "rest_ritual.h"
#include <cassert>
#include <iostream>

// 真实绘图函数在模拟画布上检查边界：不能盖住状态栏或底部任务。
struct Canvas {
 int pixels=0;
 void point(int x,int y){assert(x>=12&&x<308&&y>=32&&y<166);pixels++;}
 void fillCircle(int x,int y,int r,uint16_t){point(x-r,y-r);point(x+r,y+r);}
 void drawEllipse(int x,int y,int rx,int ry,uint16_t){point(x-rx,y-ry);point(x+rx,y+ry);}
 uint16_t color565(int r,int g,int b){assert(r>=0&&r<=255&&g>=0&&g<=255&&b>=0&&b<=255);return 0xffff;}
};
int main(){
 DeviceSettings s;assert(s.skin==0);
 for(int l=0;l<4;l++)for(int r=0;r<5;r++)for(int p=0;p<2;p++)for(int w=0;w<2;w++)for(int d=0;d<2;d++)
 for(int f=0;f<3;f++)for(int a=0;a<2;a++)for(int g=0;g<2;g++)for(int c=0;c<2;c++){
  uint32_t old=0x57030000u|l|(r<<4)|(p<<8)|(w<<9)|(d<<10)|(f<<11)|(a<<13)|(g<<14)|(c<<15);
  s.skin=1;assert(s.load(old)&&s.skin==0);assert((s.packed()&0xfff7)==(old&0xffff)&&s.focusMotion);
  for(int skin=0;skin<2;skin++){
   assert(s.setAll(l,r,p,w,d,f,a,g,c,skin));DeviceSettings copy;assert(copy.load(s.packed())&&copy.packed()==s.packed());
  }
 }
 auto before=s.packed();
 for(uint32_t bad:{0x57040008u,0x57040080u,0x57041800u,0x57040050u,0x57060000u})assert(!s.load(bad)&&s.packed()==before);
 assert(!patchDeviceSettings(s,"0","-","-","-","-","-","-","-","-","2")&&s.packed()==before);
 assert(patchDeviceSettings(s,"-","-","-","-","-","-","-","-","-","0")&&s.skin==0);
 assert(SettingsLayout::hit(236,95,4)==SettingHit::skin&&SettingsLayout::hit(236,145,4)==SettingHit::none);
 assert(SettingsLayout::change(s,SettingHit::skin)&&s.skin==1);
 assert(patchDeviceSettings(s,"1","-","-","-","-","1","1","1","1")&&s.skin==1); // 旧九字段客户端保留新外观。
 assert(SettingsLayout::change(s,SettingHit::skin)&&s.skin==0);
 Canvas canvas;
 for(int mood=0;mood<=int(FaceMood::rest);mood++)for(int next=0;next<=int(FaceMood::rest);next++)
 for(int t=0;t<=20;t++)for(int breathing:{-2,2}){
  auto pose=mixPose(poseFor(FaceMood(mood)),poseFor(FaceMood(next)),t/20.0f);
  drawCatSkin(canvas,pose,153,98,t/20.0f,breathing,1234,0xffff);
  drawCatSkin(canvas,pose,167,99,t/20.0f,breathing,1234,0xffff);
 }
 auto sleep=poseFor(FaceMood::rest);RestRitual ritual;ritual.update(true,false,false,poseFor(FaceMood::idle),0);
 for(uint32_t t=0;t<=3200;t+=20)drawCatSkin(canvas,ritual.frame(sleep,t),160,99,1,2,t,0xffff);
 assert(canvas.pixels>10000);
 std::cout<<"Cat skin: legacy settings preserved, persistence, partial updates and animated geometry stay inside face area\n";
}
