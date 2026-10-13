#pragma once
#include <stdint.h>

// 连续触摸只触发一次；抬手后才能重触发。启动时先见到松手，不在开机瞬间运动。
class PetContact {
    bool pressed=false,armed=false,emitted=false,tracking=false;
    uint32_t changed=0;
public:
    bool update(bool down,uint32_t now){
        if(!tracking||down!=pressed){tracking=true;pressed=down;changed=now;}
        if(!down){if(uint32_t(now-changed)>=400){armed=true;emitted=false;}return false;}
        if(armed&&!emitted&&uint32_t(now-changed)>=120){emitted=true;armed=false;return true;}
        return false;
    }
    bool rearmed()const{return armed;}
    void cancel(uint32_t now){armed=false;emitted=true;tracking=false;changed=now;}
};

inline int petTrajectory(int from,int to,uint32_t elapsed){
    if(elapsed>=800)return to;
    float t=elapsed/800.0f,s=t*t*(3-2*t);
    float value=from+(to-from)*s;
    return int(value+0.5f);
}
