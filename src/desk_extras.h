#pragma once
#include <string>
#include <vector>
#include <stdint.h>
#include "list_scroll.h"

struct RecapRow {std::string id,kind,title;};
struct DeskExtras {
 uint32_t token=0,recapAt=0,musicAt=0;bool partial=false,musicPresent=false,playing=false,armed=false;
 std::vector<RecapRow> rows;
 std::string player,key,title,artist;uint32_t elapsed=0,duration=0;
 int page=0;ListScroll scroll;
 uint32_t serial=0,eventAt=0,resultAt=0;bool pending=false,inFlight=false;
 std::string action,target,eventToken,result;
 bool recapLive(uint32_t now)const{return token&&!rows.empty()&&uint32_t(now-recapAt)<8000;}
 bool musicLive(uint32_t now)const{return musicPresent&&uint32_t(now-musicAt)<8000;}
 void clear(){rows.clear();musicPresent=playing=armed=pending=inFlight=false;page=0;}
 void setRecap(uint32_t id,bool incomplete,const std::vector<RecapRow>& next,uint32_t now){
  if(id!=token){scroll.reset(now);if(page==1)page=0;}
  token=id;partial=incomplete;rows=next;recapAt=now;scroll.rowHeight=56;scroll.viewportHeight=128;scroll.resize(int(rows.size()));
 }
 uint32_t progress(uint32_t now)const{return musicLive(now)?std::min(duration,elapsed+(playing?uint32_t(now-musicAt)/1000:0)):0;}
 bool request(const std::string& kind,const std::string& value,uint32_t now){
  if(!armed||inFlight)return false;
  if(++serial==0)++serial;action=kind;target=value;eventToken=std::to_string(token);
  eventAt=now;pending=inFlight=true;result="pending";resultAt=now;return true;
 }
 void tick(uint32_t now){
  if(inFlight&&uint32_t(now-eventAt)>6000){pending=inFlight=false;result="failed";resultAt=now;}
  if(page==1)scroll.tick(now);
 }
 static int entry(int x,int y){if(y<28||y>=64)return 0;if(x>=12&&x<112)return 1;if(x>=116&&x<224)return 2;return 0;}
 static int musicButton(int x,int y){return y>=198&&y<240&&x>=12&&x<308?1+(x-12)/99:0;}
 const char* feedback(uint32_t now)const{
  if(result.empty()||uint32_t(now-resultAt)>5000)return "";
  if(result=="pending")return "正在请求…";
  if(result=="sent")return "已发送 · 等待播放器更新";
  if(result=="opened")return "已请求打开 Codex";
  if(result=="headphones")return "请先连接 AirPods";
  if(result=="stale")return "内容已变化，请重试";
  if(result=="locked")return "请先解锁 Mac";
  if(result=="ok")return "已收起";
  return "暂不可用，请在 Mac 查看";
 }
};
