#pragma once
#include <algorithm>
#include <stdint.h>
#include "notice_state.h"

// 一个有版本号的整数保存所有偏好，避免掉电造成半组设置。
struct DeviceSettings {
    int light=1, rest=1, skin=0;
    const char* skinLabel()const {return skin==1?"猫系":"默认";}
    int daily=1;bool awayRest=true,greeting=true,affection=true;
    const char* dailyLabel()const {const char* names[]={"低调","自然","活泼"};return names[daily];}
    bool petMotion=true;
    bool waitMotion=false,doneMotion=false,focusMotion=true;
    int brightness()const { const int values[]={40,70,110,160};return values[light]; }
    uint32_t idleMs()const { const int minutes[]={1,3,5,10,0};return uint32_t(minutes[rest])*60000; }
    const char* lightLabel()const {const char* names[]={"柔和","标准","明亮","很亮"};return names[light];}
    const char* restLabel()const {const char* names[]={"1分","3分","5分","10分","常亮"};return names[rest];}
    bool set(int l,int r,int p){if(l<0||l>3||r<0||r>4||(p!=0&&p!=1))return false;light=l;rest=r;petMotion=p;return true;}
    bool set(int l,int r,int p,int w,int d){
        if((w!=0&&w!=1)||(d!=0&&d!=1)||!set(l,r,p))return false;
        waitMotion=w;doneMotion=d;return true;
    }
    NoticeKind notificationMotion(const NoticeEvents& event)const{
        if(waitMotion&&event.kind==NoticeKind::waiting)return NoticeKind::waiting;
        if(doneMotion&&event.completed>0)return NoticeKind::done;
        return NoticeKind::none;
    }
    bool setAll(int l,int r,int p,int w,int d,int frequency,int away,int greet,int fond,int appearance,int focus=1){
        if((focus!=0&&focus!=1)||appearance<0||appearance>1)return false;
        if(frequency<0||frequency>2||(away!=0&&away!=1)||(greet!=0&&greet!=1)||(fond!=0&&fond!=1))return false;
        if(!set(l,r,p,w,d))return false;
        daily=frequency;awayRest=away;greeting=greet;affection=fond;skin=appearance;focusMotion=focus;return true;
    }
    bool setAll(int l,int r,int p,int w,int d,int frequency,int away,int greet,int fond){return setAll(l,r,p,w,d,frequency,away,greet,fond,skin,focusMotion);}
    uint32_t packed()const{return 0x57050000u|(focusMotion?8u:0)|uint32_t(light)|(uint32_t(skin)<<2)|(uint32_t(rest)<<4)|(petMotion?0x100u:0)|(waitMotion?0x200u:0)|(doneMotion?0x400u:0)|(uint32_t(daily)<<11)|(awayRest?0x2000u:0)|(greeting?0x4000u:0)|(affection?0x8000u:0);}
    bool load(uint32_t value){
        // 旧偏好升级保留原五项，新陪伴项采用自然/开启；整组校验后才应用。
        if((value&0xFFFFFE00u)==0x57010000u)return setAll(value&15,(value>>4)&15,(value>>8)&1,0,0,1,1,1,1,0);
        if((value&0xFFFFF800u)==0x57020000u)return setAll(value&15,(value>>4)&15,(value>>8)&1,(value>>9)&1,(value>>10)&1,1,1,1,1,0);
        bool legacy=(value&0xFFFF008Cu)==0x57030000u;
        bool v4=(value&0xFFFF0088u)==0x57040000u;
        bool v5=(value&0xFFFF0080u)==0x57050000u;
        if(!legacy&&!v4&&!v5)return false;
        return setAll(value&3,(value>>4)&7,(value>>8)&1,(value>>9)&1,(value>>10)&1,(value>>11)&3,(value>>13)&1,(value>>14)&1,(value>>15)&1,legacy?0:(value>>2)&1,v5?((value>>3)&1):1);
    }
};
enum class SettingHit { none,back,section,lightDown,lightUp,restDown,restUp,pet,waiting,done,daily,away,greeting,affection,skin };
struct SettingsLayout {
    static bool entry(int x,int y){return x>=208&&x<308&&y>=28&&y<64;}
    static int nextPage(int page){return (page+1)%5;}
    static SettingHit hit(int x,int y,int page=0){
        if(x>=12&&x<132&&y>=28&&y<64)return SettingHit::back;
        if(entry(x,y))return SettingHit::section;
        if(page==4)return x>=164&&x<308&&y>=76&&y<120?SettingHit::skin:SettingHit::none;
        if(page==2){
            if(x>=164&&x<308){
                if(y>=76&&y<120)return SettingHit::daily;
                if(y>=124&&y<168)return SettingHit::away;
                if(y>=172&&y<216)return SettingHit::greeting;
            }
            return SettingHit::none;
        }
        if(page==3)return x>=164&&x<308&&y>=76&&y<120?SettingHit::affection:SettingHit::none;
        if(page==1){
            if(x>=164&&x<308&&y>=76&&y<120)return SettingHit::waiting;
            if(x>=164&&x<308&&y>=124&&y<168)return SettingHit::done;
            return SettingHit::none;
        }
        bool down=x>=164&&x<208,up=x>=264&&x<308;
        if(y>=76&&y<120)return down?SettingHit::lightDown:up?SettingHit::lightUp:SettingHit::none;
        if(y>=124&&y<168)return down?SettingHit::restDown:up?SettingHit::restUp:SettingHit::none;
        if(y>=172&&y<216&&x>=164&&x<308)return SettingHit::pet;
        return SettingHit::none;
    }
    static bool change(DeviceSettings& s,SettingHit hit){
        auto old=s.packed();
        if(hit==SettingHit::lightDown)s.light=std::max(0,s.light-1);
        if(hit==SettingHit::lightUp)s.light=std::min(3,s.light+1);
        if(hit==SettingHit::restDown)s.rest=std::max(0,s.rest-1);
        if(hit==SettingHit::restUp)s.rest=std::min(4,s.rest+1);
        if(hit==SettingHit::pet)s.petMotion=!s.petMotion;
        if(hit==SettingHit::waiting)s.waitMotion=!s.waitMotion;
        if(hit==SettingHit::done)s.doneMotion=!s.doneMotion;
        if(hit==SettingHit::daily)s.daily=(s.daily+1)%3;
        if(hit==SettingHit::away)s.awayRest=!s.awayRest;
        if(hit==SettingHit::greeting)s.greeting=!s.greeting;
        if(hit==SettingHit::affection)s.affection=!s.affection;
        if(hit==SettingHit::skin)s.skin=1-s.skin;
        return s.packed()!=old;
    }
};
