#pragma once
#include "notice_state.h"
#include <algorithm>
#include <stdint.h>

// 只管理屏幕待机；USB、触摸和任务接收一直运行，不控制电机或音频。
class StandbyState {
    bool resting_=false;
    uint32_t activeAt_=0,fadeAt_=0,fadeMs_=1;
    float from_=70,to_=70;
    int awake_=70;
    uint32_t idleLimit_=180000;
    void target(float value,uint32_t duration,uint32_t now){
        if(to_==value)return;
        from_=brightness(now);to_=value;fadeAt_=now;fadeMs_=duration;
    }
public:
    enum : uint32_t { idleMs=180000,wakeMs=240 };
    enum : int { awakeBrightness=70 };
    void begin(uint32_t now){activeAt_=fadeAt_=now;resting_=false;from_=to_=awake_;fadeMs_=1;}
    void configure(int level,uint32_t idle,uint32_t now){awake_=std::max(40,std::min(160,level));idleLimit_=idle;wake(now);}
    bool resting()const{return resting_;}
    uint32_t idleFor(uint32_t now)const{return uint32_t(now-activeAt_);}
    float brightness(uint32_t now)const{
        float t=std::min(1.0f,uint32_t(now-fadeAt_)/float(fadeMs_));
        return from_+(to_-from_)*t*t*(3-2*t);
    }
    void wake(uint32_t now){activeAt_=now;resting_=false;target(awake_,wakeMs,now);}
    // 休息只改变表情，背光始终沿用用户设置的亮度。
    void settle(uint32_t){resting_=true;}
    // 普通心跳、时钟和聊天表情变化不重置空闲计时。
    void observe(const std::vector<Task>& previous,const std::vector<Task>& next,
                 bool wasConnected,uint32_t now){
        bool event=!wasConnected;
        for(const auto& task:next){
            auto it=std::find_if(previous.begin(),previous.end(),[&](const Task& old){return old.id==task.id;});
            if(it==previous.end()||(task.state=="running"&&it->state!="running"))event=true;
        }
        if(event)wake(now);
    }
    void tick(uint32_t now,bool connected,const std::vector<Task>& tasks,bool interacting){
        bool busy=interacting;
        if(connected)for(const auto& task:tasks)busy=busy||task.state=="running"||task.state=="needs_input";
        if(busy){wake(now);return;}
        if(idleLimit_&&!resting_&&idleFor(now)>=idleLimit_)settle(now);
    }
};

// 休息后的首次接触整段只唤醒，抬手前不会变成点击或列表拖动。
struct WakeTouchGate {
    bool consumed=false;
    void begin(StandbyState& standby,uint32_t now){consumed=standby.resting();standby.wake(now);}
    void end(){consumed=false;}
};
