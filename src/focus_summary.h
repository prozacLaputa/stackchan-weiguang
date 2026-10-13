#pragma once
#include <algorithm>
#include <stdint.h>
#include "desk_companion.h"

// 本地日期由 Mac 校准，离线后用单调时钟继续走；暂停、休息和重启空档不计入。
struct FocusDay {
 uint32_t day=0,ms=0,rounds=0;
 bool valid()const{return (day==0&&ms==0&&rounds==0)||(day>=10957&&day<=47482&&ms<=86400000&&rounds<=1440);}
};
struct FocusSummary {
 static constexpr uint64_t dayMs=86400000ULL;
 FocusDay today,previous;bool ready=false,dirty=false,initialized=false;
 uint64_t localMs=0;uint32_t lastAt=0;
 FocusDay& record(uint32_t day){
  if(today.day!=day){
   if(previous.day==day)std::swap(today,previous);
   else{previous=today;today=FocusDay{};today.day=day;}
   dirty=true;
  }
  return today;
 }
 void add(uint64_t start,uint64_t end){
  while(start<end){
   uint32_t day=start/dayMs;uint64_t stop=std::min(end,(uint64_t(day)+1)*dayMs);
   auto& entry=record(day);entry.ms=std::min(uint32_t(dayMs),entry.ms+uint32_t(stop-start));dirty=true;start=stop;
  }
 }
 void sample(uint32_t now,const FocusCycle& timer){
  uint32_t dt=initialized?uint32_t(now-lastAt):0;lastAt=now;initialized=true;
  if(!ready)return;
  localMs+=dt;
  if(timer.working()){
   uint32_t since=now-timer.started,budget=timer.total*1000-timer.elapsed;
   uint32_t begin=since>dt?since-dt:0,end=std::min(since,budget);
   if(end>begin)add(localMs-(since-begin),localMs-(since-end));
   // sample 必须先于 FocusCycle::tick；该轮随后进入休息，不会重复累计。
   if(since>=budget){auto& entry=record(uint32_t((localMs-(since-budget))/dayMs));entry.rounds=std::min(1440u,entry.rounds+1);dirty=true;}
  }
  record(uint32_t(localMs/dayMs));
 }
 bool sync(uint32_t localSeconds,uint32_t now,const FocusCycle& timer){
  if(localSeconds<946684800u||localSeconds>4102444799u)return false;
  sample(now,timer);localMs=uint64_t(localSeconds)*1000;ready=true;record(localSeconds/86400u);return true;
 }
 uint32_t seconds()const{return ready?today.ms/1000:0;}
 uint32_t rounds()const{return ready?today.rounds:0;}
 uint32_t day()const{return ready?today.day:0;}
 // 显式 32 位字段，避免结构体对齐差异；单个 NVS blob 原子保存，带版本和校验。
 void encode(uint32_t (&words)[8])const{
  words[0]=0x46530101;words[1]=today.day;words[2]=today.ms;words[3]=today.rounds;
  words[4]=previous.day;words[5]=previous.ms;words[6]=previous.rounds;words[7]=checksum(words);
 }
 static uint32_t checksum(const uint32_t* words){uint32_t hash=2166136261u;for(int i=0;i<7;i++){hash^=words[i];hash*=16777619u;}return hash;}
 bool load(const uint32_t (&words)[8]){
  FocusDay a,b;a.day=words[1];a.ms=words[2];a.rounds=words[3];b.day=words[4];b.ms=words[5];b.rounds=words[6];
  if(words[0]!=0x46530101||words[7]!=checksum(words)||!a.valid()||!b.valid()||(a.day&&a.day==b.day))return false;
  today=a;previous=b;dirty=false;return true;
 }
};
