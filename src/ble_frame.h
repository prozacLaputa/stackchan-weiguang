#pragma once
#include <stdint.h>
#include <string>

// 每帧: WG + 版本1 + 正文长度(大端16位)；正文=序号4 + 密文 + GCM标签16。
struct BleFrame {
 static constexpr size_t maxPlain=4096,maxBody=maxPlain+20;
 std::string buffer;
 uint32_t lastByte=0;
 void clear(){buffer.clear();}
 bool append(const uint8_t* data,size_t size,uint32_t now,std::string& frame){
  if(!buffer.empty()&&uint32_t(now-lastByte)>3000)clear();
  lastByte=now;
  if(size>512||buffer.size()+size>maxBody+5){clear();return false;}
  buffer.append(reinterpret_cast<const char*>(data),size);
  if(buffer.size()<5)return false;
  auto b=reinterpret_cast<const uint8_t*>(buffer.data());
  size_t length=(size_t(b[3])<<8)|b[4];
  if(b[0]!='W'||b[1]!='G'||b[2]!=1||length<20||length>maxBody){clear();return false;}
  if(buffer.size()<length+5)return false;
  if(buffer.size()!=length+5){clear();return false;}
  frame.swap(buffer);buffer.clear();return true;
 }
};
