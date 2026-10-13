#pragma once
#include <algorithm>
#include <stdint.h>
#include <string>

// 只移动完整字符串的绘制原点，不按字节切割中文或 Emoji。
// 触摸／滚动时取消，停稳后从句首重新等待；心跳不会重置阅读。
struct ProgressMarquee {
    std::string key;
    int index=-1,offset=0,travel=0;
    uint32_t since=0;
    static constexpr uint32_t startHold=1600,endHold=2000,pixelMs=50;

    bool tick(const std::string& nextKey,int nextIndex,int textWidth,int viewport,
              uint32_t now,bool allowed){
        int previousIndex=index,previousOffset=offset;
        int distance=std::max(0,textWidth-viewport);
        if(!allowed||nextKey.empty()||viewport<=0||distance==0){
            key.clear();index=-1;offset=travel=0;
        }else{
            if(key!=nextKey||index!=nextIndex||travel!=distance){
                key=nextKey;index=nextIndex;travel=distance;since=now;offset=0;
            }
            uint32_t duration=uint32_t(travel)*pixelMs;
            uint32_t phase=uint32_t(now-since)%(startHold+duration+endHold);
            offset=phase<startHold?0:std::min(travel,int((phase-startHold)/pixelMs));
        }
        return previousIndex!=index||previousOffset!=offset;
    }
};
