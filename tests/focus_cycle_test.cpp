#include "desk_companion.h"
#include <cassert>
#include <iostream>
int main(){
 FocusCycle c;assert(c.phase==FocusTimer::off&&c.round==0&&!c.next(0));
 c.start(1500,100);assert(c.round==1&&c.working()&&c.focusTotal==1500);
 c.tick(1500099);assert(c.remaining(1500099)==1&&!c.resting());
 c.tick(1500100);assert(c.resting()&&c.phase==FocusTimer::running&&c.remaining(1500100)==300);
 assert(c.completions==1&&c.focusCompletions==1&&c.finished(1500100));
 assert(!c.next(1500100)&&c.round==1);
 assert(c.pause(1560100));assert(c.remaining(1760100)==240);
 c.tick(9999999);assert(c.phase==FocusTimer::paused&&c.completions==1);
 assert(c.resume(2000000));c.tick(2239999);assert(c.remaining(2239999)==1);
 c.tick(2240000);assert(c.phase==FocusTimer::done&&c.resting()&&c.completions==2&&c.focusCompletions==1);
 c.tick(3000000);assert(c.round==1&&c.phase==FocusTimer::done&&!c.finished(3000000));
 assert(c.next(3000001)&&c.round==2&&c.working()&&c.remaining(3000001)==1500);
 assert(!c.finished(3000001)&&!c.next(3000002));
 c.stop();c.tick(9999999);assert(c.phase==FocusTimer::off&&c.round==0&&!c.resting());
 c.start(60,100);c.tick(400100);assert(c.phase==FocusTimer::done&&c.resting()&&c.round==1);
 assert(c.focusCompletions==2&&c.completions==4); // 迟到时不生成多轮或重复完成。
 c.tick(9999999);assert(c.focusCompletions==2&&c.completions==4);
 c.start(60,0);assert(!c.pause(60000)&&c.resting()&&c.phase==FocusTimer::running);
 c.stop();c.tick(900000);assert(c.phase==FocusTimer::off);
 c.start(60,UINT32_MAX-1000);c.tick(58999);assert(c.resting()&&c.remaining(58999)==300);
 c.tick(358999);assert(c.phase==FocusTimer::done&&c.finished(358999));
 assert(c.next(360000)&&c.round==2&&c.remaining(360000)==60);
 assert(c.pause(361000));auto completions=c.completions;c.stop();c.tick(900000);assert(c.completions==completions);
 std::cout<<"专注转休息、暂停精度、下一轮、取消、迟到与回绕边界通过\n";
}
