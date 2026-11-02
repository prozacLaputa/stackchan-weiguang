#pragma once
#include <algorithm>
#include <stdint.h>
#include <string>
#include <vector>

// 时长独立存储；编辑常用项不改变正在进行的计时。
struct FocusPresets {
 static constexpr int defaultMinutes=30,maxMinutes=240,maxCustom=6;
 uint32_t revision=0;std::vector<int> custom;
 static bool valid(int value){return value>=1&&value<=maxMinutes;}
 static bool builtin(int value){return value==30||value==60||value==120;}
 const char* update(uint32_t expected,bool add,int value,FocusPresets& next)const{
  if(expected!=revision)return "conflict";
  if(!valid(value)||(!add&&builtin(value)))return "invalid";
  next=*this;auto item=std::find(next.custom.begin(),next.custom.end(),value);
  if(add){
   if(builtin(value)||item!=next.custom.end())return "";
   if(next.custom.size()>=maxCustom)return "full";
   next.custom.push_back(value);std::sort(next.custom.begin(),next.custom.end());
  }else{if(item==next.custom.end())return "";next.custom.erase(item);}
  next.revision=revision==UINT32_MAX?1:revision+1;return "";
 }
 std::string csv()const{std::string s;for(int v:custom){if(!s.empty())s+=",";s+=std::to_string(v);}return s.empty()?"-":s;}
 static uint32_t checksum(const uint32_t* w){uint32_t h=2166136261u;for(int i=0;i<9;i++)h=(h^w[i])*16777619u;return h;}
 void encode(uint32_t* w)const{std::fill(w,w+10,0);w[0]=0x57465001;w[1]=revision;w[2]=custom.size();for(size_t i=0;i<custom.size();i++)w[3+i]=custom[i];w[9]=checksum(w);}
 bool load(const uint32_t* w){
  if(w[0]!=0x57465001||w[2]>maxCustom||w[9]!=checksum(w)||(w[2]&&!w[1]))return false;
  FocusPresets next;next.revision=w[1];
  for(size_t i=0;i<maxCustom;i++){
   if(i>=w[2]){if(w[3+i])return false;continue;}
   int v=w[3+i];if(!valid(v)||builtin(v)||(!next.custom.empty()&&v<=next.custom.back()))return false;
   next.custom.push_back(v);
  }
  *this=next;return true;
 }
};
