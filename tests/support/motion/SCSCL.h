#pragma once
#include <vector>
constexpr int UART_NUM_1=1,SCSCL_MIN_ANGLE_LIMIT_L=9,SCSCL_MAX_ANGLE_LIMIT_L=11,SCSCL_TORQUE_ENABLE=40;
struct FakeServo {int zero=573,pos=659,torque=0,load=0,clock=0,readyAt=0,ioReadyAt=0,releaseAttempts=0,missingReleaseReplies=0;bool readOk=true,writeOk=true,releaseOk=true,powered=true,stuck=false,deferWrites=false;std::vector<int> targets;};
extern FakeServo fake;
struct TestSerial {template<class... T>void printf(const char*,T...){}void println(const char*){}};
extern TestSerial Serial;
inline void delay(int ms){fake.clock+=ms;}
class SCSCL {
public:
 bool begin(int,int,int,int){return true;}
 int getState(){return 0;}
 int getLastError(){return 0;}
 int FeedBack(int){return fake.readOk?15:-1;}
 int ReadPos(int){return fake.pos;}
 int ReadLoad(int){return fake.load;}
 int ReadMove(int){return 0;}
 int readByte(int,int){return fake.powered&&fake.clock>=fake.readyAt?fake.torque:-1;}
 int readWord(int,int reg){return reg==SCSCL_MIN_ANGLE_LIMIT_L?20:1003;}
 int EnableTorque(int id,int value){if(!value)fake.releaseAttempts++;if(id!=2||!fake.powered||fake.clock<fake.readyAt||(!value&&!fake.releaseOk))return 0;fake.torque=value;if(!value&&fake.missingReleaseReplies-->0)return 0;return 1;}
 int WritePos(int id,int pos,int duration,int speed){
  if(!fake.writeOk||id!=2||(duration!=600&&duration!=60)||speed!=0)return 0;
  fake.targets.push_back(pos);if(!fake.stuck&&!fake.deferWrites)fake.pos=pos;return 1;
 }
};
