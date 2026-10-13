#pragma once
#include <stdint.h>
#include <string>
#include <vector>
#include <algorithm>
#include "list_scroll.h"
#include "notice_state.h"

struct UiState {
    std::vector<Task> tasks;
    int currentIndex=0;
    ListScroll scroll;
    bool details=false,celebrating=false;
    uint32_t currentSince=0,celebratedAt=0;
    NoticeTracker notices;
    UnreadCompletions unread;
    NoticeEvents latestNotice;
    uint32_t noticeSerial=0;
    int completedCount=0;
    void returnHome(uint32_t now) { details=false;currentSince=now;scroll.reset(now); }
    void open(uint32_t now) { details=true;scroll.reset(now); }
    void update(const std::vector<Task>& next,uint32_t now,bool live=true) {
        // 刷新时保留顶端可见任务及行内偏移，避免定期数据重排把阅读位置拉回顶部。
        int anchorIndex=int(scroll.offset)/scroll.rowHeight;
        std::string anchor=details&&scroll.offset>0&&anchorIndex<int(tasks.size())?tasks[anchorIndex].id:"";
        float inset=scroll.offset-anchorIndex*scroll.rowHeight;
        std::string old=tasks.empty()?"":tasks[currentIndex].id;
        latestNotice=notices.observe(next,live);
        unread.observe(next,latestNotice);
        if(latestNotice.kind!=NoticeKind::none)noticeSerial++;
        tasks=next;currentIndex=0;bool kept=false;
        for(int i=0;i<int(tasks.size());i++)if(tasks[i].id==old){currentIndex=i;kept=true;}
        if(!kept)celebrating=false;
        if(latestNotice.completed){
            celebrating=true;celebratedAt=now;completedCount=latestNotice.completed;
            for(int i=0;i<int(tasks.size());i++)if(tasks[i].id==latestNotice.completedId)currentIndex=i;
        }
        if(!anchor.empty())for(int i=0;i<int(tasks.size());i++)if(tasks[i].id==anchor){scroll.offset=i*scroll.rowHeight+inset;break;}
        scroll.resize(int(tasks.size()));
        tick(now);
        // 待回应优先；同类任务保留当前项，避免多个问题之间来回跳动。
        int waiting=-1;
        for(int i=0;i<int(tasks.size());i++)if(tasks[i].state=="needs_input"){waiting=i;break;}
        if(waiting>=0){
            if(tasks[currentIndex].state!="needs_input")currentIndex=waiting;
            celebrating=false;
        }else if(!celebrating&&!tasks.empty()&&tasks[currentIndex].state!="running"){
            for(int i=0;i<int(tasks.size());i++)if(tasks[i].state=="running"){currentIndex=i;break;}
        }
        if(!tasks.empty()&&tasks[currentIndex].id!=old)currentSince=now;
    }
    void tick(uint32_t now) {
        if(celebrating&&uint32_t(now-celebratedAt)>=6000){
            celebrating=false;
            for(int i=0;i<int(tasks.size());i++)if(tasks[i].state=="running"){currentIndex=i;currentSince=now;break;}
        }
        if(details)scroll.tick(now);
    }
};
