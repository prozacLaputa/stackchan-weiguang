#pragma once
#include <algorithm>
#include <cstdlib>
#include <stdint.h>

struct NudgePlan {
    int origin=0,target=0,low=0,high=0;
    bool prepare(int zero,int position,int hardwareLow,int hardwareHigh,bool waiting){
        return prepareOffset(zero,position,hardwareLow,hardwareHigh,waiting?10:-10);
    }
    bool preparePet(int zero,int position,int hardwareLow,int hardwareHigh){
        return prepareOffset(zero,position,hardwareLow,hardwareHigh,48); // 15°，原厂普通抬头的下限。
    }
    bool prepareOffset(int zero,int position,int hardwareLow,int hardwareHigh,int offset){
        if(zero<0||zero>1000||hardwareLow<0||hardwareHigh>1023||hardwareHigh<=hardwareLow)return false;
        // 官方映射每步 0.3125°；5~85° 内，再保留原厂硬件限位。
        low=std::max(hardwareLow,zero+16);high=std::min({1000,hardwareHigh,zero+272});
        origin=position;target=origin+offset;
        return origin>=low&&origin<=high&&target>=low&&target<=high;
    }
    bool contains(int position)const{return position>=low&&position<=high&&position>=std::min(origin,target)-4&&position<=std::max(origin,target)+4;}
};

struct MotionGate {
    bool used=false;uint32_t last=0;
    bool allows(uint32_t now,uint32_t interval=20000)const{return !used||uint32_t(now-last)>=interval;}
    void record(uint32_t now){used=true;last=now;}
};
