#pragma once
#include <stdint.h>
#include <algorithm>
#include <cmath>
#include "list_reading.h"

// 逻辑位置始终有效；越界位移单独用于阻尼拉伸与回弹，不参与任务索引。
struct ListScroll {
    float offset=0,stretch=0,velocity=0;
    int count=0,rowHeight=TaskRow::height,viewportHeight=162;
    bool held=false;
    uint32_t lastTick=0,lastMotion=0;
    float maximum() const { return float(std::max(0,count*rowHeight-viewportHeight)); }
    float clamp(float value) const { return std::max(0.0f,std::min(value,maximum())); }
    float visualOffset() const { return offset+stretch; }
    bool moving() const { return std::fabs(velocity)>=5||std::fabs(stretch)>=0.2f; }
    void position(float value) {
        value=std::max(-38.0f,std::min(value,maximum()+38.0f));
        offset=clamp(value);stretch=value-offset;
    }
    void resize(int items) {
        bool changed=count!=items;count=items;
        float bounded=clamp(offset);
        if(changed){stretch=0;if(bounded!=offset||count==0)velocity=0;}
        offset=bounded;
    }
    void reset(uint32_t now) { offset=stretch=velocity=0;held=false;lastTick=lastMotion=now; }
    void begin(uint32_t now) { held=true;velocity=0;lastTick=lastMotion=now; }
    void drag(int fingerDeltaY,uint32_t now) {
        if(!held||!fingerDeltaY||count==0)return;
        float before=visualOffset(),delta=-float(fingerDeltaY),next=before+delta;
        // 向边缘外拉时阻力渐增；往回拖立即响应，避免越界死区。
        if((before<0&&delta<0)||(before>maximum()&&delta>0))
            next=before+delta*0.42f/(1+std::fabs(stretch)/20);
        else if(before>=0&&before<=maximum()){
            if(next<0)next*=0.42f;
            else if(next>maximum())next=maximum()+(next-maximum())*0.42f;
        }
        position(next);
        float dt=float(std::max(uint32_t(8),uint32_t(now-lastMotion)))/1000.0f;
        float sample=std::max(-1200.0f,std::min(1200.0f,(visualOffset()-before)/dt));
        velocity=0.65f*sample+0.35f*velocity;
        lastMotion=lastTick=now;
    }
    void end(uint32_t now) {
        held=false;
        if(uint32_t(now-lastMotion)>80)velocity=0;
        lastTick=now;
    }
    void tick(uint32_t now) {
        uint32_t elapsed=uint32_t(now-lastTick);lastTick=now;
        if(held)return;
        float dt=float(std::min(elapsed,uint32_t(64)))/1000.0f;
        if(std::fabs(stretch)>0.01f){
            // 临界阻尼弹簧：有弹性但不反复振荡，首尾仍不导航。
            float old=stretch,b=velocity+18.0f*old,decay=std::exp(-18.0f*dt);
            float next=(old+b*dt)*decay;
            velocity=(velocity-18.0f*b*dt)*decay;
            if(next*old<=0||(std::fabs(next)<0.2f&&std::fabs(velocity)<5)){stretch=velocity=0;}
            else{stretch=std::max(-38.0f,std::min(38.0f,next));}
        }else{
            stretch=0;
            if(std::fabs(velocity)<5){velocity=0;return;}
            float decay=std::exp(-4.4f*dt);
            position(offset+velocity*(1.0f-decay)/4.4f);velocity*=decay;
        }
    }
};
