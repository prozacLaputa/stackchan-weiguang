#pragma once
#include "pet_interaction.h"
#include <cstring>

// 只观察既有触摸门槛；不增加动作、重试、硬件轮询或持久写入。
class PetFeedback {
    PetContact contact;
    bool down=false;
    uint32_t at=0;
public:
    uint32_t event=0;
    bool sensorOK=false,screen=false;
    const char* result="none";
    const char* reason="none";
    bool held()const{return down;}
    bool rearmed()const{return contact.rearmed();}
    uint32_t age(uint32_t now)const{return event?uint32_t(now-at)/1000:0;}
    bool pending()const{return std::strcmp(result,"detected")==0;}
    void mark(const char* outcome,const char* why){result=outcome;reason=why;}
    void finish(uint32_t id,const char* outcome,const char* why){if(id&&id==event)mark(outcome,why);}
    bool update(int raw,bool screenTouch,bool active,uint32_t now){
        sensorOK=raw>=0;screen=screenTouch;
        if(raw>0&&!down){
            if(++event==0)++event;
            at=now;mark("detected","settling");
            if(screenTouch)mark("skipped","screen-touch");
            else if(active)mark("skipped","busy");
            else if(!contact.rearmed())mark("skipped","release-required");
        }
        if(raw<=0&&down&&pending())mark("skipped",raw<0?"head-read":"too-short");
        down=raw>0;
        if(screenTouch||active||raw<0){
            contact.cancel(now);
            if(pending())mark("skipped",raw<0?"head-read":screenTouch?"screen-touch":"busy");
            return false;
        }
        return contact.update(down,now);
    }
};
