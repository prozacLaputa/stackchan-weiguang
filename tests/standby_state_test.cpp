#include "../src/standby_state.h"
#include "../src/ui_state.h"
#include "../src/face_expression.h"
#include <cassert>
#include <cmath>
#include <iostream>

int main(){
    std::vector<Task> idle={{"one","done","已结束","d1","","idle"}};
    StandbyState s;s.begin(0);
    // 每秒收到任务和表情心跳，仍按实际空闲时长休息。
    for(uint32_t now=0;now<180000;now+=1000){s.observe(idle,idle,true,now);s.tick(now,true,idle,false);assert(!s.resting());}
    s.tick(180000,true,idle,false);assert(s.resting()&&s.brightness(180000)==70);
    assert(s.brightness(180900)==70&&s.brightness(181800)==70);
    s.observe(idle,idle,true,190000);s.tick(190000,true,idle,false);assert(s.resting());
    auto renamed=idle;renamed[0].title="标题变化";renamed[0].mood="joy";
    s.observe(idle,renamed,true,190001);assert(s.resting());

    // 第一次触摸消耗整个手势：不打开主页、不返回、不改变列表阅读位置。
    UiState ui;ui.update(idle,0,false);WakeTouchGate gate;
    gate.begin(s,190002);assert(gate.consumed&&!s.resting()&&!ui.details);
    s.tick(190500,true,idle,true);assert(gate.consumed);gate.end();
    gate.begin(s,190510);assert(!gate.consumed);ui.open(190510);gate.end();
    ui.scroll.offset=75;
    s.tick(370511,true,idle,false);assert(s.resting());
    gate.begin(s,370512);assert(gate.consumed&&ui.details&&ui.scroll.offset==75);gate.end();

    // 运行/待回应在实时连接期间常亮；即使没有新事件也不睡。
    for(const char* state:{"running","needs_input"}){
        auto active=idle;active[0].state=state;s.begin(0);
        s.tick(500000,true,active,false);assert(!s.resting());
        s.tick(679999,true,idle,false);assert(!s.resting());
        s.tick(680000,true,idle,false);assert(s.resting());
        s.tick(680010,true,active,false);assert(!s.resting());
        assert(s.brightness(680250)==70);
        // 断连的运行快照不阻止待机；重连恢复实时状态后唤醒。
        s.wake(700000);s.tick(880000,false,active,false);assert(s.resting());
        s.observe(active,active,false,880001);assert(!s.resting());
    }
    // 新增任务 / 原任务新一轮 / 通知，均从休息恢复。
    s.begin(0);s.tick(180000,true,idle,false);auto added=idle;added.push_back({"two","done","新任务","","","idle"});
    s.observe(idle,added,true,182000);assert(!s.resting());
    s.tick(362000,true,added,false);assert(s.resting());auto running=added;running[0].state="running";
    s.observe(added,running,true,362001);assert(!s.resting());
    s.tick(542001,true,added,false);assert(s.resting());
    ui.update(idle,542002,false);auto completed=idle;completed[0].doneKey="d2";
    ui.update(completed,542003,true);assert(ui.latestNotice.completed==1);
    if(ui.latestNotice.kind!=NoticeKind::none)s.wake(542003);
    s.tick(542003,true,completed,ui.celebrating);assert(!s.resting());

    // 四档亮度在空闲休息、锁屏休息、反复心跳及唤醒过程中都保持不变。
    for(int level:{40,70,110,160}){
        StandbyState bright;bright.configure(level,180000,0);bright.begin(0);
        bright.tick(180000,true,idle,false);assert(bright.resting());
        for(uint32_t now:{180000u,180900u,181800u,300000u})assert(bright.brightness(now)==level);
        bright.wake(300001);assert(!bright.resting()&&bright.brightness(300001)==level);
        bright.settle(300002);bright.settle(300003);assert(bright.resting()&&bright.brightness(302000)==level);
        bright.tick(302001,true,idle,true);assert(!bright.resting()&&bright.brightness(302001)==level);
    }
    // 手动改亮度依旧平滑生效，休息/唤醒不会将其拉低。
    StandbyState manual;manual.begin(0);manual.configure(110,180000,100);
    assert(manual.brightness(100)==70);manual.settle(150);
    assert(manual.brightness(220)>70&&manual.brightness(340)==110);
    manual.wake(341);assert(manual.brightness(341)==110);
    // millis 回绕，包括持续运行超过整个计时周期的极端情况。
    s.begin(UINT32_MAX-100000);s.tick(79998,true,idle,false);assert(!s.resting());
    s.tick(79999,true,idle,false);assert(s.resting());assert(s.brightness(81799)==70);
    s.tick(81800,true,idle,true);assert(!s.resting());

    FaceAnimator face;face.update(FaceMood::rest,2000);
    assert(face.update(FaceMood::rest,2500).eyeHeight>1);
    auto rest=face.update(FaceMood::rest,3000);assert(rest.eyeHeight==1&&rest.mouthCurve>0);
    face.update(FaceMood::idle,3100);assert(face.update(FaceMood::idle,3480).eyeHeight==10);
    assert(!knownExpression("rest")); // 聊天文本不能直接强制设备休息。
    std::cout<<"Standby: heartbeat, wake events, offline snapshots, touch isolation, constant rest brightness and clock wrap passed\n";
}
