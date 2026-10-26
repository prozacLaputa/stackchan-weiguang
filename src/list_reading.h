#pragma once
#include <stdint.h>
#include <algorithm>
#include <cmath>
#include <string>
#include <vector>
#include "notice_state.h"

namespace TaskRow {
constexpr int height=80,cardTop=2,cardHeight=72,titleTop=8,lineHeight=18,titleHeight=34,statusTop=48;
}

// UTF-8 按完整字符换行；宽度由实际屏幕字体测量，不按字节截断中文。
template<class Measure>
std::vector<std::string> wrapTaskTitle(const std::string& title,int width,Measure measure){
    std::vector<std::string> lines;std::string line;
    for(size_t p=0;p<title.size();){
        unsigned char c=title[p];size_t n=c<0x80?1:c<0xE0?2:c<0xF0?3:4;
        n=std::min(n,title.size()-p);std::string next=title.substr(p,n);p+=n;
        if(!line.empty()&&measure(line+next)>width){lines.push_back(line);line.clear();}
        line+=next;
    }
    if(!line.empty())lines.push_back(line);
    return lines;
}

inline bool rowFullyVisible(int index,float offset,int rowHeight,int viewport){
    float top=index*rowHeight-offset;
    return top>=0&&top+rowHeight<=viewport;
}

class UnreadCompletions {
    struct Entry {std::string id;bool viewing=false;uint32_t since=0;};
    std::vector<Entry> entries;
public:
    uint32_t revision=0;
    int count() const{return int(entries.size());}
    bool contains(const std::string& id)const{
        for(const auto& e:entries)if(e.id==id)return true;return false;
    }
    void observe(const std::vector<Task>& tasks,const NoticeEvents& event){
        for(auto it=entries.begin();it!=entries.end();){
            auto task=std::find_if(tasks.begin(),tasks.end(),[&](const Task&t){return t.id==it->id;});
            // 未知数据保留标记；已开始新一轮、已移出当前列表则清理旧标记。
            if(task==tasks.end()||(task->state!="done"&&task->state!="unknown")){it=entries.erase(it);revision++;}
            else ++it;
        }
        for(const auto& id:event.completedIds){
            auto task=std::find_if(tasks.begin(),tasks.end(),[&](const Task&t){return t.id==id;});
            if(task==tasks.end()||task->state!="done")continue;
            auto it=std::find_if(entries.begin(),entries.end(),[&](const Entry&e){return e.id==id;});
            if(it==entries.end()){Entry e;e.id=id;entries.push_back(e);}
            else it->viewing=false;
            revision++;
        }
    }
    void readVisible(const std::vector<Task>& tasks,float offset,int rowHeight,int viewport,uint32_t now,bool allowed){
        for(auto it=entries.begin();it!=entries.end();){
            int index=-1;for(int i=0;i<int(tasks.size());i++)if(tasks[i].id==it->id){index=i;break;}
            bool visible=allowed&&index>=0&&rowFullyVisible(index,offset,rowHeight,viewport);
            if(!visible){it->viewing=false;++it;continue;}
            if(!it->viewing){it->viewing=true;it->since=now;}
            if(uint32_t(now-it->since)>=1200){it=entries.erase(it);revision++;}
            else ++it;
        }
    }
};

// 每次只展开一条完整可见的长标题；触屏、惯性、待机或离开列表立即复位。
struct TitlePlayback {
    std::string key;int index=-1,offset=0;uint32_t since=0;
    bool tick(const std::string& nextKey,int nextIndex,int lineCount,uint32_t now,bool allowed){
        int beforeIndex=index,beforeOffset=offset;
        if(!allowed||lineCount<=2){key.clear();index=-1;offset=0;}
        else{
            if(key!=nextKey||index!=nextIndex){key=nextKey;index=nextIndex;since=now;offset=0;}
            uint32_t elapsed=now-since;offset=0;
            if(elapsed>=1200){
                int steps=lineCount-2;uint32_t phase=(elapsed-1200)%(uint32_t(steps)*2*2450);
                int leg=phase/2450;float progress=std::min(1.0f,float(phase%2450)/650);
                progress=progress*progress*(3-2*progress);
                float line=leg<steps?leg+progress:2*steps-leg-progress;
                offset=int(std::lround(line*TaskRow::lineHeight));
            }
        }
        return beforeIndex!=index||beforeOffset!=offset;
    }
};
