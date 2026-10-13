#pragma once
#include <string>
#include "device_settings.h"

// '-' 表示保持设备当前值，只应用用户修改的字段；整个补丁先校验再生效。
inline bool patchDeviceSettings(DeviceSettings& current,const std::string& light,const std::string& rest,const std::string& pet,const std::string& waiting="-",const std::string& done="-",const std::string& daily="-",const std::string& away="-",const std::string& greeting="-",const std::string& affection="-",const std::string& skin="-",const std::string& focus="-"){
    const std::string values[]={light,rest,pet,waiting,done,daily,away,greeting,affection,skin,focus};int next[]={current.light,current.rest,current.petMotion?1:0,current.waitMotion?1:0,current.doneMotion?1:0,current.daily,current.awayRest?1:0,current.greeting?1:0,current.affection?1:0,current.skin,current.focusMotion?1:0};
    bool changed=false;
    for(int i=0;i<11;i++){
        if(values[i]=="-")continue;
        if(values[i].size()!=1||values[i][0]<'0'||values[i][0]>'9')return false;
        next[i]=values[i][0]-'0';changed=true;
    }
    if(!changed)return false;
    return current.setAll(next[0],next[1],next[2],next[3],next[4],next[5],next[6],next[7],next[8],next[9],next[10]);
}
