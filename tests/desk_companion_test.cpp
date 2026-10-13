#include "desk_companion.h"
#include "standby_state.h"
#include <cassert>
#include <iostream>
int main(){
 FocusTimer f;assert(f.phase==FocusTimer::off&&f.remaining(0)==0);
 f.start(60,100);assert(f.remaining(100)==60&&f.remaining(1099)==60&&f.remaining(1100)==59);
 f.tick(60099);assert(f.phase==FocusTimer::running&&f.remaining(60099)==1);
 f.tick(60100);assert(f.phase==FocusTimer::done&&f.finished(60100)&&f.remaining(60100)==0);
 f.tick(70100);assert(!f.finished(70100));
 f.start(1500,80000);f.tick(80000+600000);assert(f.remaining(680000)==900); // No link/panel dependency.
 f.stop();f.tick(9000000);assert(f.phase==FocusTimer::off&&f.total==0);
 f.start(60,UINT32_MAX-1000);f.tick(58999);assert(f.phase==FocusTimer::done&&f.finished(59000));
 DeskCompanion d;assert(std::string(d.presence(0))=="unknown");
 assert(!d.accept("awake",0,100));assert(!d.welcome(100)); // Startup is not a return.
 d.accept("away",0,200);assert(d.away(201));
 assert(d.accept("awake",123,300));assert(d.welcome(300));
 assert(!d.accept("awake",123,4000));assert(!d.welcome(6300)); // Heartbeats cannot replay greeting.
 d.accept("awake",0,8000);d.accept("awake",123,9000);assert(!d.welcome(9000));
 d.accept("away",0,10000);assert(!d.welcome(10000));
 assert(!d.away(22000));assert(std::string(d.presence(22000))=="unknown");
 d.accept("awake",456,23000);assert(d.welcome(23000));d.dismissWelcome();assert(!d.welcome(23001));
 d.accept("away",0,UINT32_MAX-1000);assert(d.away(100));assert(!d.away(11000));
 StandbyState s;s.begin(0);s.settle(1000);assert(s.resting());
 s.settle(2000);assert(s.brightness(2800)==70);s.wake(2800);assert(!s.resting()&&s.brightness(3040)==70);
 std::cout<<"Local focus completion/cancel/wrap, presence lease and greeting deduplication passed\n";
}
