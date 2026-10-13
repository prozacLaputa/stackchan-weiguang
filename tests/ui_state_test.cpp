#include "../src/ui_state.h"
#include "../src/touch_gesture.h"
#include <cassert>
#include <iostream>

Task task(const char*id,const char*state="done"){return {id,state,id,"",""};}
bool near(float a,float b){return std::fabs(a-b)<0.01f;}
std::vector<Task> tasks(){return {task("a","running"),task("b"),task("c"),task("d"),task("e"),task("f"),task("g"),task("h")};}

void scrolling(){
 UiState u;u.update(tasks(),100);u.open(200);
 TouchGesture g;g.begin(150,200,200);u.scroll.begin(200);
 // 上划时内容立即跟随手指，不等抬手、不按页跳转。
 u.scroll.drag(g.move(148,170),230);assert(near(u.scroll.offset,30));
 u.scroll.drag(g.move(149,140),260);assert(near(u.scroll.offset,60));
 auto release=g.release(149,130,280);assert(!release.tap);
 u.scroll.drag(release.dragY,280);u.scroll.end(280);
 assert(near(u.scroll.offset,70));u.tick(312);assert(u.scroll.offset>70&&u.details&&u.currentIndex==0);
 // 再次按住立即打断惯性，向下拖查看前面的内容。
 float stopped=u.scroll.offset;u.scroll.begin(320);u.tick(352);assert(near(u.scroll.offset,stopped));
 u.scroll.drag(20,380);assert(near(u.scroll.offset,stopped-20));
 u.scroll.end(600);u.tick(632);assert(near(u.scroll.offset,stopped-20)); // 停稳后抬手不再甩动。
 // 边界不循环、不返回；触底后反向拖动立即生效。
 u.scroll.begin(700);u.scroll.drag(-1000,750);assert(near(u.scroll.offset,u.scroll.maximum())&&u.scroll.stretch>0&&u.details);
 float edge=u.scroll.visualOffset();u.scroll.drag(15,780);assert(near(u.scroll.visualOffset(),edge-15));
 u.scroll.drag(1000,810);u.scroll.end(820);u.tick(900);assert(near(u.scroll.offset,0)&&u.scroll.stretch<0&&u.details);
 for(uint32_t now=932;now<2000;now+=32)u.tick(now);
 assert(u.scroll.stretch==0&&u.scroll.velocity==0&&u.details);
 // 快速甩动最终停止，并始终位于内容范围内。
 u.scroll.begin(3000);u.scroll.drag(-35,3020);u.scroll.end(3020);
 for(uint32_t now=3052;now<6000;now+=32){u.tick(now);assert(u.scroll.offset>=0&&u.scroll.offset<=u.scroll.maximum()&&std::fabs(u.scroll.stretch)<=38&&u.details);}
 assert(u.scroll.velocity==0);
 u.tick(100000);assert(u.details);u.returnHome(100001);assert(!u.details);
}

void touchAndLayout(){
 TouchGesture g;ListLayout l{320,240};
 g.begin(100,100,100);assert(g.move(104,101)==0);assert(g.release(103,100,180).tap);
 // 左右滑均不触发导航；从返回按钮开始拖动也不能变为点击。
 g.begin(30,40,200);assert(g.move(90,42)==0);assert(!g.release(30,40,300).tap);
 g.begin(250,150,400);assert(g.move(100,148)==0);assert(!g.release(100,148,600).tap);
 g.begin(100,150,700);assert(g.move(99,170)==20);assert(g.move(100,150)==-20);assert(!g.release(100,150,800).tap);
 g.begin(40,40,900);assert(!g.release(40,40,1600).tap);
 assert(l.hit(25,45)==Hit::back&&l.hit(95,30)==Hit::back&&l.hit(126,30)==Hit::none);
 assert(l.hit(260,45)==Hit::none&&!l.inRows(30,40));
 for(int y=l.rowsTop();y<240;y++)for(int x=0;x<320;x++)assert(l.hit(x,y)==Hit::none);
 assert(l.inRows(100,200)&&l.viewportHeight()==162&&l.rowHeight()==TaskRow::height&&l.rowHeight()==72);
 // 回归：先横向偏 10px，再上划，不应被永久锁死；轻微斜划和 4px 起滑。
 g.begin(150,180,1700);assert(g.move(160,177)==0);assert(g.move(161,120)==-60);assert(!g.release(161,120,1800).tap);
 g.begin(150,180,1900);assert(g.move(154,176)==-4);assert(!g.release(154,176,1920).tap);
 // 主屏与返回按钮保留点击容差，不能因为列表的低起滑门槛变得难点。
 g.begin(50,40,2000,false);assert(g.move(51,46)==0);assert(g.release(51,46,2050).tap);
 g.begin(50,40,2100,false);g.move(51,60);assert(!g.release(51,40,2200).tap);
 assert(l.inRows(150,238)&&!l.inRows(30,40));
}

void liveUpdates(){
 UiState u;u.update(tasks(),100);u.open(200);u.scroll.offset=2*TaskRow::height+10; // c 行偏移 10px。
 auto changed=tasks();changed.insert(changed.begin(),task("new"));
 u.update(changed,300);assert(near(u.scroll.offset,3*TaskRow::height+10)&&u.tasks[int(u.scroll.offset)/TaskRow::height].id=="c");
 assert(u.currentIndex==1&&u.details);
 changed[1].state="done";changed[1].doneKey="turn-a";changed[4].state="running";
 u.update(changed,400);assert(u.celebrating&&u.currentIndex==1);
 u.update(changed,6500);assert(!u.celebrating&&u.currentIndex==4&&u.details&&near(u.scroll.offset,3*TaskRow::height+10));
 // 数据收缩、删除锚点、清空时不越界；无需滚动的短列表也不退出。
 u.update({task("z"),task("q")},5000);assert(u.scroll.offset==0&&u.scroll.maximum()==0&&u.details);
 u.scroll.begin(5100);u.scroll.drag(-100,5150);u.scroll.end(5160);u.tick(5200);assert(u.scroll.offset==0&&u.details);
 u.update({},5300);assert(u.currentIndex==0&&u.scroll.offset==0&&u.details);
 u.returnHome(5400);u.open(5500);assert(u.scroll.offset==0&&u.details);
 // 顶部刷新不偷偷定位到旧首项；再次打开从头浏览。
 u.update(tasks(),5600);u.update(changed,5700);assert(u.scroll.offset==0);
 u.scroll.offset=140;u.returnHome(5800);u.open(5900);assert(u.scroll.offset==0);
}

void rollover(){
 UiState u;u.update(tasks(),UINT32_MAX-200);u.open(UINT32_MAX-100);
 u.scroll.begin(UINT32_MAX-100);u.scroll.drag(-40,UINT32_MAX-40);u.scroll.end(UINT32_MAX-20);
 u.tick(20);assert(u.scroll.offset>40&&u.scroll.offset<u.scroll.maximum()&&u.details);
 TouchGesture g;g.begin(30,40,UINT32_MAX-100);assert(g.release(31,40,30).tap);
}

void springRefresh(){
 UiState u;u.update(tasks(),100);u.open(200);u.scroll.begin(210);u.scroll.drag(60,240);
 float pulled=u.scroll.stretch;assert(pulled<0&&pulled>-60);
 u.update(u.tasks,250);assert(near(u.scroll.stretch,pulled)&&u.scroll.held);
 u.scroll.end(350);
 for(uint32_t now=360;now<1600;now+=16)u.tick(now);
 assert(u.scroll.stretch==0&&u.scroll.offset==0&&u.scroll.velocity==0&&u.details);
 u.scroll.begin(1700);u.scroll.drag(70,1740);u.update({},1750);assert(u.scroll.stretch==0&&u.scroll.offset==0);
}

void waitingPriority(){
 UiState u;auto next=tasks();u.update(next,100);u.open(200);u.scroll.offset=122;
 next[4].state="needs_input";u.update(next,300);
 assert(u.currentIndex==4&&!u.celebrating&&u.details&&near(u.scroll.offset,122));
 // 多个问题出现时不来回抢焦点，也不强制退出正在浏览的列表。
 next[2].state="needs_input";u.update(next,400);assert(u.currentIndex==4);
 next[4].state="running";u.update(next,500);assert(u.currentIndex==2);
 next[2].state="done";u.update(next,600);assert(u.currentIndex==0&&!u.celebrating&&u.details);
 // 完成笑脸不能盖住另一项真实的待回应提醒。
 next[0].state="done";next[7].state="needs_input";u.update(next,700);
 assert(u.currentIndex==7&&!u.celebrating&&near(u.scroll.offset,122));
 next[7].state="done";u.update(next,800);assert(!u.celebrating&&u.tasks[u.currentIndex].state=="running");
 u.update({},900);assert(u.currentIndex==0&&u.details);
}

int main(){scrolling();touchAndLayout();liveUpdates();rollover();springRefresh();waitingPriority();std::cout<<"Responsive scrolling, spring, touch safety, live-update and waiting-priority tests passed\n";}
