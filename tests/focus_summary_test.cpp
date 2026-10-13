#include "focus_summary.h"
#include <cassert>
#include <iostream>
static const uint32_t stamp=20738u*86400u+12*3600u;
void advance(FocusSummary& s,FocusCycle& f,uint32_t now){s.sample(now,f);f.tick(now);}
int main(){
 FocusSummary s;FocusCycle f;s.sync(stamp,0,f);f.start(60,0);
 advance(s,f,10000);assert(s.seconds()==10&&s.rounds()==0);
 // 暂停和休息不计入；提前结束保留实际毫秒，下一次不会重复计数。
 f.pause(10000);advance(s,f,50000);assert(s.seconds()==10);f.resume(50000);
 advance(s,f,60000);f.stop();advance(s,f,80000);assert(s.seconds()==20&&s.rounds()==0);
 f.start(60,80000);advance(s,f,140000);assert(s.seconds()==80&&s.rounds()==1&&f.resting());
 advance(s,f,140000);advance(s,f,440000);assert(s.seconds()==80&&s.rounds()==1);
 assert(f.next(440000));advance(s,f,470000);assert(s.seconds()==110&&s.rounds()==1);
 advance(s,f,500000);assert(s.seconds()==140&&s.rounds()==2);
 // 正常断连无需新同步；跨午夜按真实专注区间拆分，整轮归于结束日。
 FocusSummary midnight;FocusCycle cross;
 uint32_t day=20738;midnight.sync(day*86400u+86390,0,cross);cross.start(60,0);
 advance(midnight,cross,70000);
 assert(midnight.day()==day+1&&midnight.seconds()==50&&midnight.rounds()==1);
 assert(midnight.previous.day==day&&midnight.previous.ms==10000&&midnight.previous.rounds==0);
 advance(midnight,cross,370000);assert(midnight.seconds()==50);
 // 恰好午夜完成：前一天用时、新一天完成轮数；仅空闲跨日会归零。
 FocusSummary exact;FocusCycle e;exact.sync(day*86400u+86340,0,e);e.start(60,0);advance(exact,e,60000);
 assert(exact.seconds()==0&&exact.rounds()==1&&exact.previous.ms==60000);
 e.stop();advance(exact,e,86460000);assert(exact.seconds()==0&&exact.rounds()==0);
 // 保存 / 重启还原、未知日期隐藏、同日恢复、下一日清空、旧日短时回拨保留。
 uint32_t words[8];s.encode(words);FocusSummary loaded;assert(loaded.load(words));
 FocusCycle empty;assert(!loaded.ready&&loaded.seconds()==0);loaded.sync(stamp+501,100,empty);
 assert(loaded.seconds()==140&&loaded.rounds()==2);
 loaded.sync(stamp+86400,200,empty);assert(loaded.seconds()==0);
 loaded.sync(stamp+502,300,empty);assert(loaded.seconds()==140&&loaded.rounds()==2);
 words[3]^=1;FocusSummary corrupt;assert(!corrupt.load(words));
 s.encode(words);words[2]=86400001;words[7]=FocusSummary::checksum(words);assert(!corrupt.load(words));
 assert(!loaded.sync(0,400,empty));
 // 未同步不伪造“今天”，第一次同步之前的时间不补算。
 FocusSummary unknown;FocusCycle u;u.start(60,0);advance(unknown,u,10000);assert(!unknown.ready&&unknown.seconds()==0);
 unknown.sync(stamp,10000,u);advance(unknown,u,20000);assert(unknown.seconds()==10);
 // 接近 millis 溢出、非整秒暂停、迟到tick均只累计真实专注区间。
 FocusSummary wrap;FocusCycle w;uint32_t origin=UINT32_MAX-1000;wrap.sync(stamp,origin,w);w.start(60,origin);
 advance(wrap,w,origin+60000);assert(wrap.seconds()==60&&wrap.rounds()==1);
 FocusSummary fine;FocusCycle z;fine.sync(stamp,0,z);z.start(60,0);advance(fine,z,777);z.pause(777);
 advance(fine,z,10000);z.resume(10000);advance(fine,z,10223);assert(fine.seconds()==1);
 // 高频重复读和时钟重校准不会重复累计 / 凭空完成。
 for(int i=0;i<20;i++){advance(fine,z,10223);fine.sync(stamp+10,10223,z);}
 assert(fine.seconds()==1&&fine.rounds()==0);
 advance(fine,z,500000);assert(fine.seconds()==60&&fine.rounds()==1&&z.phase==FocusTimer::done);
 std::cout<<"Daily summary actual time, completion, midnight, offline, persistence and wrap passed\n";
}
