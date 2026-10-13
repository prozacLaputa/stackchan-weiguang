#include "progress_marquee.h"
#include "touch_gesture.h"
#include "ui_state.h"
#include <cassert>
#include <iostream>

void timeline(){
 ProgressMarquee p;
 assert(p.tick("task\nprogress",0,408,288,100,true));assert(p.offset==0&&p.travel==120);
 assert(!p.tick("task\nprogress",0,408,288,1699,true));
 p.tick("task\nprogress",0,408,288,1750,true);assert(p.offset==1);
 p.tick("task\nprogress",0,408,288,4700,true);assert(p.offset==60);
 p.tick("task\nprogress",0,408,288,7700,true);assert(p.offset==120);
 p.tick("task\nprogress",0,408,288,9699,true);assert(p.offset==120);
 p.tick("task\nprogress",0,408,288,9700,true);assert(p.offset==0);
 for(uint32_t now=9700;now<30000;now+=13){p.tick("task\nprogress",0,408,288,now,true);assert(p.offset>=0&&p.offset<=120);}
}
void cancellation(){
 ProgressMarquee p;p.tick("a",1,500,268,0,true);p.tick("a",1,500,268,5600,true);assert(p.offset==80);
 // 触摸、惯性、页面／状态退出均使用同一 allowed 门槛，立即复位。
 assert(p.tick("a",1,500,268,5601,false));assert(p.index==-1&&p.offset==0);
 p.tick("a",1,500,268,8000,true);p.tick("a",1,500,268,9599,true);assert(p.offset==0);
 p.tick("a",1,500,268,12600,true);assert(p.offset==60);
 p.tick("new text",1,500,268,12601,true);assert(p.offset==0);
 p.tick("new text",1,500,268,16601,true);assert(p.offset==48);
 p.tick("new text",0,500,268,16602,true);assert(p.offset==0); // 重排索引变化。
 p.tick("new text",0,500,240,20000,true);assert(p.offset==0); // 可用宽度变化。
 p.tick("short",0,268,268,20001,true);assert(p.index==-1);
 p.tick("",0,500,268,20002,true);assert(p.index==-1);
 p.tick("bad viewport",0,500,0,20003,true);assert(p.index==-1);
}
void wrapAndGestures(){
 ProgressMarquee p;uint32_t start=UINT32_MAX-500;
 std::string key="中文进展😀";
 p.tick(key,0,400,268,start,true);p.tick(key,0,400,268,start+2600,true);
 assert(p.offset==20&&p.key==key); // 时钟回绕不会跳至句尾，也不切割 UTF-8。
 TouchGesture gesture;gesture.begin(120,130,100,true);
 p.tick(key,0,400,268,101,!gesture.active);assert(p.index==-1);
 auto dy=gesture.move(120,80);assert(dy==-50);auto result=gesture.release(120,80,200);
 assert(!result.tap); // 文字动画没有吞掉滑动，手势判定保持。
 UiState u;std::vector<Task> tasks(4,{"id","running","任务","","","idle","","",key});
 for(int i=0;i<4;i++)tasks[i].id=std::to_string(i);
 u.update(tasks,0,false);u.open(0);u.scroll.offset=72;
 auto old=u.scroll.offset;auto notice=u.noticeSerial;
 for(uint32_t now=0;now<12000;now+=50){p.tick(key,1,400,268,now,true);u.update(tasks,now);}
 assert(u.scroll.offset==old&&u.noticeSerial==notice); // 心跳不移动列表、不新增提醒。
}
int main(){timeline();cancellation();wrapAndGestures();std::cout<<"Progress marquee: dwell, speed, end hold, reset, wrap, UTF-8 and touch isolation passed\n";}
