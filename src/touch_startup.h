#pragma once
#include <cstdint>

struct TouchStartupResult { bool ready=false,recovered=false; };

template<class Io> bool touchControllerReady(Io& io){
 uint8_t identity[6]={0};
 return io.read(0x38,0xA3,identity,6)&&identity[0]!=0&&identity[0]!=0xFF&&identity[5]!=0&&identity[5]!=0xFF;
}

template<class Io> TouchStartupResult initializeTouchController(Io& io){
 TouchStartupResult result;
 if(!touchControllerReady(io)){
  // CoreS3: AW9523 P0_0 = TOUCH_RST。软重启主控不会复位这个独立芯片。
  // 只在启动检测失败时恢复，保留同寄存器中的功放/USB 等其他引脚。
  uint8_t id=0,output=0;
  if(!io.read(0x58,0x10,&id,1)||id!=0x23||!io.read(0x58,0x02,&output,1))return result;
  bool asserted=io.write(0x58,0x02,output&~1);
  io.wait(10);
  bool released=io.write(0x58,0x02,output|1);
  if(!released)released=io.write(0x58,0x02,output|1);
  io.wait(200);
  if(!asserted||!released)return result;
  result.recovered=true;
 }
 result.ready=touchControllerReady(io)&&io.reinitialize();
 return result;
}
