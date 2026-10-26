#include "task_navigation.h"
#include "desktop_actions.h"
#include <cassert>
#include <iostream>
Task make(const char* id,const char* state){return {id,state,id,"d1","q1","idle"};}
int main(){
 UiState u;u.update({make("recent","running"),make("old","running"),make("done","done")},100);
 assert(homeTaskTarget(u,true)->id=="recent");assert(!homeTaskTarget(u,false));
 auto tasks=u.tasks;tasks[2].doneKey="d2";u.update(tasks,200);
 assert(u.celebrating&&homeTaskTarget(u,true)->id=="done");
 tasks[1].state="needs_input";u.update(tasks,210);assert(homeTaskTarget(u,true)->id=="old");
 tasks[1].state="done";tasks[0].state="done";u.update(tasks,220);u.tick(7000);
 assert(homeTaskTarget(u,true)->id=="done");
 tasks[0].state="unknown";u.update(tasks,7100);assert(!homeTaskTarget(u,true));
 u.update({make("a","running"),make("b","done"),make("c","interrupted")},8000);u.open(8000);
 ListLayout layout{320,240};assert(TaskRow::height-TaskRow::cardHeight==8);
 assert(taskCardAt(layout,0,3,100,80)==0&&taskCardAt(layout,0,3,100,160)==1);
 for(int y=142;y<154;y++)assert(taskCardAt(layout,0,3,100,y)==-1);
 assert(taskCardAt(layout,0,3,14,80)==-1&&taskCardAt(layout,0,3,305,80)==-1);
 assert(taskCardAt(layout,0,3,100,60)==-1&&taskCardAt(layout,0,3,100,235)==-1);
 assert(taskCardAt(layout,80,3,100,80)==1);
 assert(taskCardAt(layout,-20,3,100,80)==-1);
 assert(!listTaskTarget(u,false,100,80));
 TouchGesture g;TaskPress press;
 auto begin=[&](){g.begin(100,80,100,false);press.begin(listTaskTarget(u,true,100,80),true,taskListRegion,100,80);};
 for(const auto* state:{"running","done","needs_input","interrupted","unknown"}){
  u.tasks[0].state=state;begin();assert(press.captured);
  assert(!press.poll(listTaskTarget(u,true,100,80),true,g,100,80,399));
  assert(press.poll(listTaskTarget(u,true,100,80),true,g,100,80,400)&&g.active);
  assert(!press.poll(listTaskTarget(u,true,100,80),true,g,100,80,1000));
 }
 begin();std::swap(u.tasks[0],u.tasks[1]);press.observe(listTaskTarget(u,true,100,80),true);
 std::swap(u.tasks[0],u.tasks[1]);assert(!press.poll(listTaskTarget(u,true,100,80),true,g,100,80,400));
 begin();press.observe(listTaskTarget(u,true,100,147),true);assert(!press.poll(listTaskTarget(u,true,100,80),true,g,100,80,400));
 begin();g.scrollEnabled=true;g.move(100,85);assert(!press.poll(listTaskTarget(u,true,100,85),true,g,100,85,400));
 u.tasks[0].state="done";begin();u.tasks[0].doneKey="d2";assert(!press.poll(listTaskTarget(u,true,100,80),true,g,100,80,400));
 begin();assert(!press.poll(listTaskTarget(u,true,100,80),false,g,100,80,400));
 u.scroll.velocity=90;press.begin(listTaskTarget(u,true,100,80),!u.scroll.moving(),taskListRegion,100,80);assert(!press.captured);
 WaitingPress waiting;waiting.begin(&u.tasks[0],true,waitingRegion,100,180);assert(!waiting.captured);
 DesktopAction a;a.armed=true;assert(a.request("a",100,true)&&a.anyTask);a.queued=false;
 assert(a.finish(a.serial,"stale",101));assert(std::string(a.feedback(102))=="会话已不在当前列表");a.reset();assert(!a.anyTask);
 std::cout<<"Task navigation: status targets, card gaps, held dispatch, scroll/reorder cancellation and explicit scope passed\n";
}
