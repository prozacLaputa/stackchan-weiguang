#include "../src/touch_startup.h"
#include <cassert>
#include <vector>
#include <iostream>
struct Io {
 bool ready=false,readFails=false,driverOk=true,releaseFails=false,low=false;
 uint8_t output=0xA7,awId=0x23;
 int resets=0,reinitializations=0;
 std::vector<int> writes,waits;
 bool read(uint8_t addr,uint8_t reg,uint8_t* data,int count){
  if(readFails)return false;
  if(addr==0x38){for(int i=0;i<count;i++)data[i]=0;if(ready){data[0]=0x64;data[5]=0x11;}return true;}
  data[0]=reg==0x10?awId:output;return true;
 }
 bool write(uint8_t,uint8_t,uint8_t value){
  writes.push_back(value);if(releaseFails&&(value&1))return false;
  output=value;if(!(value&1))low=true;else if(low){low=false;ready=true;resets++;}return true;
 }
 void wait(int ms){waits.push_back(ms);}
 bool reinitialize(){reinitializations++;return ready&&driverOk;}
};
int main(){
 // 实机故障模式：总线 ACK 成功，但识别信息全零；主控重启不改变此状态。
 Io stuck;auto restored=initializeTouchController(stuck);
 assert(restored.ready&&restored.recovered&&stuck.resets==1);
 assert((stuck.writes==std::vector<int>{0xA6,0xA7})); // 仅改变触摸复位位。
 assert((stuck.waits==std::vector<int>{10,200}));
 Io healthy;healthy.ready=true;auto unchanged=initializeTouchController(healthy);
 assert(unchanged.ready&&!unchanged.recovered&&healthy.writes.empty());
 Io failed;failed.readFails=true;assert(!initializeTouchController(failed).ready&&failed.writes.empty());
 Io wrong;wrong.awId=0;assert(!initializeTouchController(wrong).ready&&wrong.writes.empty());
 Io noRelease;noRelease.releaseFails=true;assert(!initializeTouchController(noRelease).ready);
 assert(noRelease.writes.size()==3); // 释放失败仅补一次，不无限重试复位。
 Io driver;driver.driverOk=false;assert(!initializeTouchController(driver).ready);
 std::cout<<"Touch startup recovery checks passed\n";
}
