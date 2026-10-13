#pragma once
#include <stdint.h>
enum class SyncTransport { usb,ble };
struct SyncState {
 bool linked=false,available=false,ever=false;
 SyncTransport transport=SyncTransport::usb;
 uint32_t packetAt=0,goodAge=0;
 int goodSeconds=-1;
 void accept(uint32_t now,SyncTransport via,bool dataOk,int good,uint32_t age){
  uint32_t retainedAge=this->age(now);
  linked=true;ever=true;available=dataOk;transport=via;packetAt=now;
  if(good>=0){goodSeconds=good;goodAge=age;}else goodAge=retainedAge;
 }
 bool expire(uint32_t now){if(linked&&uint32_t(now-packetAt)>15000){linked=false;return true;}return false;}
 bool live()const{return linked&&available;}
 const char* title()const{return !linked?"等待 Mac":!available?"数据异常":transport==SyncTransport::ble?"蓝牙同步":"USB 同步";}
 uint32_t age(uint32_t now)const{return goodAge+uint32_t(now-packetAt)/1000;}
};
