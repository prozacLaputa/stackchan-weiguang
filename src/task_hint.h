#pragma once
#include <string>
#include "notice_state.h"

inline bool validTaskHint(const std::string& text){
    if(text.size()>128)return false;
    for(size_t i=0;i<text.size();){
        unsigned char c=text[i++];
        if(c<0x20||c==0x7f)return false;
        if(c<0x80)continue;
        int extra=c>=0xc2&&c<=0xdf?1:c>=0xe0&&c<=0xef?2:c>=0xf0&&c<=0xf4?3:-1;
        if(extra<0||i+extra>text.size())return false;
        unsigned char first=text[i];
        if((c==0xe0&&first<0xa0)||(c==0xed&&first>=0xa0)||(c==0xf0&&first<0x90)||(c==0xf4&&first>=0x90))return false;
        for(int j=0;j<extra;j++)if((static_cast<unsigned char>(text[i++])&0xc0)!=0x80)return false;
    }
    return true;
}

inline std::string waitingHint(const Task& task,bool live){
    return live&&task.state=="needs_input"?task.waitReason:"";
}

inline std::string taskHint(const Task& task,bool live){
    if(!live)return "";
    if(task.state=="needs_input")return task.waitReason;
    if(task.state=="running")return task.progressHint;
    return task.state=="done"?task.resultHint:"";
}

// 用实际字体宽度截短，保留完整 UTF-8 字符；不改变任务行高度和手势。
template<class Measure>
std::string fitTaskHint(const std::string& text,int width,Measure measure){
    if(measure(text)<=width)return text;
    std::string result;
    for(size_t i=0;i<text.size();){
        unsigned char c=text[i];size_t count=c<0x80?1:c<0xe0?2:c<0xf0?3:4;
        if(i+count>text.size())break;
        std::string next=text.substr(i,count);
        if(measure(result+next+"…")>width)break;
        result+=next;i+=count;
    }
    return measure("…")<=width?result+"…":"";
}
