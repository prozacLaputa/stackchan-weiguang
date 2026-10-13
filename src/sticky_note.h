#pragma once
#include <stdint.h>
#include <string>
#include "touch_gesture.h"

// 便签只有一张；收起保留正文，以便 Mac 重新贴上。修订号避免旧请求覆盖新内容。
struct StickyNote {
 uint32_t revision=0;std::string state="empty",text;
 bool active()const{return state=="active";}
 static bool allowed(uint32_t cp){return (cp>=0x20&&cp<=0x7e)||(cp>=0xa0&&cp<=0x24f)||(cp>=0x2010&&cp<=0x2027)||(cp>=0x3000&&cp<=0x303f)||(cp>=0x4e00&&cp<=0x9fff)||(cp>=0xff01&&cp<=0xff60);}
 static bool validText(const std::string& value){
  if(value.empty()||value.size()>96)return false;
  unsigned count=0;bool visible=false;
  for(size_t i=0;i<value.size();){
   uint8_t first=value[i++];uint32_t cp=0;int more=0;
   if(first<0x80)cp=first;
   else if(first>=0xc2&&first<=0xdf){cp=first&31;more=1;}
   else if(first>=0xe0&&first<=0xef){cp=first&15;more=2;}
   else return false;
   if(i+more>value.size())return false;
   for(int j=0;j<more;j++){uint8_t c=value[i++];if((c&0xc0)!=0x80)return false;cp=(cp<<6)|(c&63);}
   if((more==1&&cp<0x80)||(more==2&&cp<0x800)||!allowed(cp)||++count>32)return false;
   visible|=cp!=0x20&&cp!=0xa0&&cp!=0x3000;
  }
  return visible;
 }
 const char* update(uint32_t expected,const std::string& action,const std::string& value,StickyNote& next)const{
  if(expected!=revision)return "conflict";
  next=*this;
  if(action=="set"){if(!validText(value))return "invalid";next.text=value;next.state="active";}
  else if(action=="done"){if(!value.empty()||state=="empty")return "invalid";next.state="done";}
  else if(action=="restore"){if(!value.empty()||state=="empty")return "invalid";next.state="active";}
  else return "invalid";
  if(next.state!=state||next.text!=text){if(revision==UINT32_MAX)return "invalid";next.revision++;}
  return "";
 }
 static std::string hex(const std::string& value){static const char* digits="0123456789abcdef";std::string out;for(uint8_t c:value){out+=digits[c>>4];out+=digits[c&15];}return out.empty()?"-":out;}
 static int nibble(char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;}
 static bool unhex(const std::string& value,std::string& out){
  out.clear();if(value=="-")return true;if(value.empty()||value.size()>192||value.size()%2)return false;
  for(size_t i=0;i<value.size();i+=2){int a=nibble(value[i]),b=nibble(value[i+1]);if(a<0||b<0)return false;out+=char(a*16+b);}return true;
 }
 static uint32_t hash(const std::string& bytes){uint32_t value=2166136261u;for(uint8_t c:bytes){value^=c;value*=16777619u;}return value;}
 static void append32(std::string& out,uint32_t value){for(int i=0;i<4;i++)out+=char(value>>(i*8));}
 static uint32_t read32(const std::string& bytes,size_t offset){uint32_t value=0;for(int i=0;i<4;i++)value|=uint32_t(uint8_t(bytes[offset+i]))<<(i*8);return value;}
 std::string encode()const{std::string out="NT01";append32(out,revision);out+=char(active()?1:state=="done"?2:0);out+=text;append32(out,hash(out));return out;}
 bool load(const std::string& bytes){
  if(bytes.size()<13||bytes.size()>109||bytes.substr(0,4)!="NT01"||read32(bytes,bytes.size()-4)!=hash(bytes.substr(0,bytes.size()-4)))return false;
  uint32_t rev=read32(bytes,4);uint8_t status=bytes[8];std::string value=bytes.substr(9,bytes.size()-13);
  if(status>2||(status==0&&(rev||!value.empty()))||(status>0&&(!rev||!validText(value))))return false;
  revision=rev;state=status==1?"active":status==2?"done":"empty";text=value;return true;
 }
};
inline bool stickyNoteRegion(int x,int y){return x>=12&&x<308&&y>=142&&y<236;}
struct StickyNotePress {
 bool captured=false,canceled=false;uint32_t revision=0;
 void begin(const StickyNote& note,bool visible,int x,int y){captured=visible&&stickyNoteRegion(x,y);canceled=false;revision=note.revision;}
 bool matches(const StickyNote& note,bool visible)const{return captured&&!canceled&&visible&&note.revision==revision;}
 void observe(const StickyNote& note,bool visible){if(captured&&!matches(note,visible))canceled=true;}
 bool release(const StickyNote& note,bool visible,const TouchGesture& gesture,int x,int y,uint32_t now)const{
  uint32_t held=now-gesture.startAt;
  return matches(note,visible)&&stickyNoteRegion(x,y)&&gesture.maxTravel<=8&&gesture.axis==Axis::pending&&held>=900&&held<=4000;
 }
};
