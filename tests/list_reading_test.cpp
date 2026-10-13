#include "../src/ui_state.h"
#include <cassert>
#include <iostream>

Task task(const char*id){return {id,"running",id,"","","idle"};}
void read(UiState&u,uint32_t now,bool allowed=true,float offset=0){u.unread.readVisible(u.tasks,offset,72,162,now,allowed);}
void unread(){
 UiState u;std::vector<Task> next={task("a"),task("b"),task("c"),task("d")};
 u.update(next,0,false);assert(u.unread.count()==0);
 for(auto&t:next){t.state="done";t.doneKey="one";}
 u.update(next,10);assert(u.unread.count()==4&&u.latestNotice.completedIds.size()==4);
 u.tick(7000);assert(!u.celebrating&&u.unread.count()==4); // 动画结束不清标记。
 u.update(next,7010);assert(u.unread.count()==4); // 心跳不重复。
 read(u,7100);read(u,8200);assert(u.unread.count()==4);
 read(u,8210,false);read(u,8300);read(u,9400);assert(u.unread.count()==4); // 划动打断阅读计时。
 read(u,9500);assert(u.unread.count()==2&&!u.unread.contains("a")&&!u.unread.contains("b"));
 read(u,9600,true,144);read(u,10800,true,144);assert(u.unread.count()==0);
 // 完成一轮后重连不补播；从未知恢复也不产生新完成。
 for(auto&t:next)t.doneKey="offline";
 u.update(next,11000,false);u.update(next,12000);assert(u.unread.count()==0);
 next[0].doneKey="two";u.update(next,13000);assert(u.unread.count()==1);
 next[0].state="unknown";u.update(next,14000,false);read(u,14000,false);read(u,20000,false);assert(u.unread.count()==1);
 next[0].state="done";u.update(next,20001,false);
 read(u,20100,true,1);read(u,24000,true,1);assert(u.unread.count()==1); // 部分可见不算看过。
 read(u,24100);read(u,26000,false);assert(u.unread.count()==1); // 设置、待机、离线同样关掉 allowed。
 read(u,26100);next[0].doneKey="three";u.update(next,27000);read(u,27100);read(u,27300);assert(u.unread.count()==1);
 read(u,28300);assert(u.unread.count()==0); // 新完成重新计时。
 next[0].doneKey="four";u.update(next,29000);next[0].state="running";u.update(next,29100);assert(u.unread.count()==0);
 next[0].state="done";next[0].doneKey="five";u.update(next,29200);next.erase(next.begin());u.update(next,29300);assert(u.unread.count()==0);
 // 新出现的历史任务只设基线。
 next.push_back({"new","done","new","old","","idle"});u.update(next,30000);assert(u.unread.count()==0);
}
void wrap(){
 auto measure=[](const std::string&s){int width=0;for(size_t i=0;i<s.size();){unsigned char c=s[i];i+=c<0x80?1:c<0xE0?2:c<0xF0?3:4;width+=c<0x80?8:16;}return width;};
 std::string source="中文 Mac 编程🙂阅读超长任务标题 ABC";
 auto lines=wrapTaskTitle(source,64,measure);std::string joined;
 for(const auto& l:lines){assert(!l.empty()&&measure(l)<=64);joined+=l;}
 assert(joined==source&&lines.size()>2);
 assert(wrapTaskTitle("",64,measure).empty());
 assert(wrapTaskTitle("中文",32,measure).size()==1);
 assert(wrapTaskTitle("ABCD",8,measure).size()==4);
 assert(rowFullyVisible(0,0,72,162)&&rowFullyVisible(1,0,72,162)&&!rowFullyVisible(2,0,72,162));
 assert(!rowFullyVisible(0,1,72,162)&&rowFullyVisible(1,1,72,162));
}
void playback(){
 TitlePlayback p;p.tick("a",0,4,100,true);assert(p.index==0&&p.offset==0);
 p.tick("a",0,4,1299,true);assert(p.offset==0);
 p.tick("a",0,4,1625,true);assert(p.offset==9);
 p.tick("a",0,4,1950,true);assert(p.offset==18);
 p.tick("a",0,4,3000,true);assert(p.offset==18);
 p.tick("a",0,4,4400,true);assert(p.offset==36);
 for(uint32_t now=4400;now<22000;now+=13){p.tick("a",0,4,now,true);assert(p.offset>=0&&p.offset<=36);}
 p.tick("a",0,4,22000,false);assert(p.index==-1&&p.offset==0);
 p.tick("a",0,4,22010,true);p.tick("a",0,4,23000,true);assert(p.offset==0);
 p.tick("changed",0,4,24000,true);assert(p.offset==0);
 p.tick("short",1,2,25000,true);assert(p.index==-1);
 p.tick("a",0,3,UINT32_MAX-500,true);p.tick("a",0,3,800,true);assert(p.offset>=0&&p.offset<18);
 UiState u;auto next=std::vector<Task>{task("a")};u.update(next,1);next[0].state="done";next[0].doneKey="done";u.update(next,2);
 read(u,UINT32_MAX-500);read(u,800);assert(u.unread.count()==0);
}
int main(){unread();wrap();playback();std::cout<<"Unread completion dwell, baseline, UTF-8 wrapping and title playback tests passed\n";}
