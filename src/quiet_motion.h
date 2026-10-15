#pragma once
#include <SCSCL.h>
#include <PY32IOExpander.hpp>
#include <Preferences.h>
#include "motion_plan.h"
#include "notice_state.h"
#include "pet_feedback.h"

// 不调用原厂归位或自动校准，只在实时事件出现时围绕实测位置做小动作。
class QuietMotion {
    SCSCL bus;
    m5::PY32IOExpander_Class power;
    NudgePlan plan;MotionGate gate,petGate;
    int phase=0,hardwareLow=-1,hardwareHigh=-1,rest=-1;
    uint32_t phaseAt=0,sampledAt=0,commandAt=0;
    bool petting=false;int commanded=-1;
    bool petEnabled=true,waitEnabled=false,doneEnabled=false,focusEnabled=false,activeFocus=false;
    uint32_t activePetEvent=0;
    const char* fault="not-initialized";
    const char* readError="none";
    const char* startReason="none";
    bool reject(const char* why){startReason=why;return false;}
    NoticeKind activeKind=NoticeKind::none;
    bool writePosition(int pos,int duration=600){return bus.WritePos(2,pos,duration,0)==1&&bus.getState()==0;}
    bool readPosition(int& pos){
        if(bus.FeedBack(2)<0||bus.getState()!=0){readError="position-read";return false;}
        pos=bus.ReadPos(-1);
        if(pos<0||pos>1000){readError="position-range";return false;}
        if(std::abs(bus.ReadLoad(-1))>=(petting?500:650)){readError="load-high";return false;}
        readError="none";return true;
    }
    bool release(){
        if(bus.EnableTorque(2,0)==1&&bus.getState()==0)return true;
        // 总线无回执时切断舵机电源，不能只在软件里标记停止。
        power.digitalWrite(0,false);ready=false;fault="release-ack";return false;
    }
    void fail(const char* reason){
        fault=reason;release();phase=0;ready=false;startReason=fault;
        feedback.finish(activePetEvent,"failed",fault);activePetEvent=0;
        Serial.printf("MOTION\tstopped\t%s\n",reason);
    }
public:
    PetFeedback feedback;
    bool ready=false,enabled=true;
    int zero=-1;
    void begin(){
        if(!bus.begin(UART_NUM_1,1000000,6,7)){fault="bus-init";return;}
        // 扩展芯片和舵机可能晚于主控就绪；仅启动阶段有界等待，不重试运动故障。
        bool ioReady=false;
        for(int attempt=0;attempt<6;attempt++){
            if(power.begin()){ioReady=true;break;}
            delay(200);
        }
        if(!ioReady||!power.setDirection(0,true)||!power.setPullMode(0,m5::PY32IOExpander_Class::pull_up)||!power.digitalWrite(0,true)){
            power.digitalWrite(0,false);fault="power-init";Serial.println("MOTION\tunavailable\tpower-init");return;
        }
        delay(200);
        bool released=false;
        for(int attempt=1;attempt<=8;attempt++){
            bus.EnableTorque(2,0);
            int torque=bus.readByte(2,SCSCL_TORQUE_ENABLE),readState=bus.getState();
            // 写回执不能代替状态确认；回执丢失时也必须读到扭矩为 0 且舵机无故障。
            if(torque==0&&readState==0){released=true;Serial.printf("MOTION\tready\tattempts=%d\n",attempt);break;}
            if(attempt<8)delay(200);
        }
        if(!released){power.digitalWrite(0,false);ready=false;fault="torque-release";Serial.println("MOTION\tunavailable\ttorque-release");return;}
        Preferences prefs;
        if(prefs.begin("servo",true)){zero=prefs.getInt("zero_pos_2",-1);prefs.end();}
        hardwareLow=bus.readWord(2,SCSCL_MIN_ANGLE_LIMIT_L);hardwareHigh=bus.readWord(2,SCSCL_MAX_ANGLE_LIMIT_L);
        // 需要本机原厂校准，缺失时仅显示屏幕提醒，不猜测物理零位。
        ready=zero>=0&&zero<=1000&&hardwareLow>=0&&hardwareHigh>hardwareLow&&hardwareHigh<=1023;
        fault=ready?"none":"calibration";
        inspect();
    }
    bool active()const{return phase!=0;}
    bool isPetting()const{return phase&&petting;}
    void configure(bool pet,bool waiting,bool done,bool focus=false){
        petEnabled=pet;waitEnabled=waiting;doneEnabled=done;focusEnabled=focus;
        if(phase&&!(activeFocus?focusEnabled:petting?petEnabled:activeKind==NoticeKind::waiting?waitEnabled:doneEnabled)){
            bool released=release();phase=0;feedback.finish(activePetEvent,released?"stopped":"failed",released?"preference":fault);activePetEvent=0;Serial.println("MOTION\tstopped\tpreference");
        }
    }
    bool request(NoticeKind kind,uint32_t now,bool headTouch=false,bool screenTouch=false){
        if(headTouch||screenTouch)return false;
        return start(kind,now,false);
    }
    bool requestFocus(uint32_t now,bool headTouch=false,bool screenTouch=false){
        if(headTouch||screenTouch)return false;
        return start(NoticeKind::done,now,false,true);
    }
    bool requestPet(uint32_t now,bool fromHead=false){
        bool started=start(NoticeKind::none,now,true);
        if(started)activePetEvent=fromHead?feedback.event:0;
        if(fromHead)feedback.mark(started?"moving":ready?"skipped":"failed",started?"none":startReason);
        return started;
    }
    uint32_t cooldown(uint32_t now)const{
        uint32_t age=uint32_t(now-petGate.last);return petGate.used&&age<5000?5000-age:0;
    }
    const char* faultReason()const{return fault;}
    const char* petState(uint32_t now)const{
        if(!ready)return "unavailable";
        if(!enabled||!petEnabled)return "disabled";
        if(!feedback.sensorOK)return "sensor";
        if(phase)return "moving";
        if(feedback.screen)return "screen";
        if(cooldown(now))return "cooldown";
        if(!feedback.rearmed())return "release";
        return "ready";
    }
    bool start(NoticeKind kind,uint32_t now,bool isPet,bool isFocus=false){
        startReason="none";
        if(!isPet&&kind==NoticeKind::none)return reject("no-event");
        if(!ready)return reject(fault);
        if(!enabled)return reject("disabled");
        if(phase)return reject("busy");
        if(!(isFocus?focusEnabled:isPet?petEnabled:kind==NoticeKind::waiting?waitEnabled:doneEnabled))return reject("preference");
        if(isPet?!petGate.allows(now,5000):!gate.allows(now))return reject("cooldown");
        activePetEvent=0;
        petting=isPet;activeKind=kind;activeFocus=isFocus;
        int position=-1;
        if(!readPosition(position)){fail(readError);return false;}
        // 小的回位误差沿用同一休息位置，避免每次点头都累积向下漂移。
        // 手动换了姿势则重新读取，以新姿势为基准。
        int anchor=rest>=0&&std::abs(position-rest)<=4?rest:position;
        bool planned=isPet?plan.preparePet(zero,anchor,hardwareLow,hardwareHigh):plan.prepare(zero,anchor,hardwareLow,hardwareHigh,kind==NoticeKind::waiting);
        bool moving=bus.ReadMove(-1)!=0;
        if(moving||!planned||!plan.contains(position)){
            Serial.println("MOTION\tskipped\tposition-range-or-moving");return reject(moving?"already-moving":"position-limit");
        }
        // 0x28 为单字节寄存器，不能用上游的双字节读取方法。
        int torque=bus.readByte(2,SCSCL_TORQUE_ENABLE);
        if(torque<0||torque>1||bus.getState()!=0){fail("torque-read");return false;}
        // 先把旧目标替换为刚读到的位置，再上力，避免启用时追逐旧目标。
        if(!writePosition(position)||bus.EnableTorque(2,1)!=1||bus.getState()!=0||(!isPet&&!writePosition(plan.target))){
            fail("command-ack");return false;
        }
        rest=anchor;gate.record(now);if(isPet)petGate.record(now);
        phase=1;phaseAt=sampledAt=commandAt=now;commanded=position;
        Serial.printf("MOTION\tstart\t%s\torigin=%d\ttarget=%d\n",isFocus?"focus":isPet?"pet":kind==NoticeKind::waiting?"waiting":"done",plan.origin,plan.target);
        return true;
    }
    void tick(uint32_t now,bool headTouch,bool screenTouch=false){
        if(!phase)return;
        // 主动抚摸动作允许头顶触摸；触屏始终停止，通知动作遇摸头也停止。
        if(screenTouch||(headTouch&&!petting)){bool released=release();phase=0;feedback.finish(activePetEvent,released?"stopped":"failed",released?"screen-touch":fault);activePetEvent=0;Serial.println("MOTION\tstopped\ttouch");return;}
        if(uint32_t(now-phaseAt)>1800){fail("timeout");return;}
        int target=phase%2?plan.target:plan.origin;
        // 反馈只能对照已经发出的目标。新指令有 60 ms 行程时间，不能刚写入就判定未跟上。
        bool sampleDue=uint32_t(now-sampledAt)>=100;
        int pos=-1;
        if(sampleDue){
            uint32_t sampleGap=uint32_t(now-sampledAt);sampledAt=now;
            if(!readPosition(pos)){fail(readError);return;}
            if(!plan.contains(pos)){fail("feedback-range");return;}
            if(petting&&std::abs(pos-commanded)>14){
                Serial.printf("MOTION\tfollow-error\tposition=%d\tcommand=%d\tcommand_age=%u\tsample_gap=%u\tphase=%d\tphase_age=%u\tload=%d\n",
                    pos,commanded,unsigned(now-commandAt),unsigned(sampleGap),phase,unsigned(now-phaseAt),bus.ReadLoad(-1));
                fail("pet-follow-error");return;
            }
        }
        if(petting&&uint32_t(now-commandAt)>=40){
            int from=phase%2?plan.origin:plan.target;
            int next=petTrajectory(from,target,now-phaseAt);
            if(next!=commanded){
                if(!writePosition(next,60)){fail("pet-command-ack");return;}
                commanded=next;
            }
            commandAt=now;
        }
        if(!sampleDue)return;
        if(uint32_t(now-phaseAt)<(petting?950u:700u))return;
        // 实机小步插值在抬头端有约 5 步死区；回位仍要求 4 步内，防止休息位置漂移。
        int tolerance=petting&&(phase%2)?6:4;
        if(std::abs(pos-target)>tolerance){
            if(petting&&uint32_t(now-phaseAt)<1500)return;
            Serial.printf("MOTION\tmiss\tphase=%d\tposition=%d\ttarget=%d\n",phase,pos,target);
            fail("not-reached");return;
        }
        if(phase<2){
            Serial.printf("MOTION\tpeak\tposition=%d\tphase=%d\n",pos,phase);
            if(!petting&&!writePosition(plan.origin)){fail("return-ack");return;}
            phase++;phaseAt=commandAt=now;
        }else{
            if(!release()){fail("release-ack");return;}
            phase=0;feedback.finish(activePetEvent,"completed","none");activePetEvent=0;Serial.printf("MOTION\tend\tposition=%d\torigin=%d\n",pos,plan.origin);
        }
    }
    void disable(){enabled=false;bool released=true;if(ready||phase)released=release();phase=0;feedback.finish(activePetEvent,released?"stopped":"failed",released?"disabled":fault);activePetEvent=0;Serial.println("MOTION\tdisabled");}
    void inspect(){
        if(!ready){Serial.println("MOTION\tunavailable");return;}
        int pos=bus.ReadPos(2),torque=bus.readByte(2,SCSCL_TORQUE_ENABLE);
        Serial.printf("MOTION\tprobe\tzero=%d\tposition=%d\ttorque=%d\tlimits=%d,%d\tenabled=%d\n",zero,pos,torque,hardwareLow,hardwareHigh,enabled);
    }
};
