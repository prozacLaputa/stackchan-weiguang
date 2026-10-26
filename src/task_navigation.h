#pragma once
#include "ui_state.h"
#include "touch_gesture.h"

// 列表按最近活跃排序；主屏跳转与正在显示的大状态一致。
inline const Task* homeTaskTarget(const UiState& ui,bool live){
 if(!live||ui.tasks.empty())return nullptr;
 for(const auto& t:ui.tasks)if(t.state=="needs_input")return &t;
 if(ui.celebrating&&ui.currentIndex>=0&&ui.currentIndex<int(ui.tasks.size())&&ui.tasks[ui.currentIndex].state=="done")return &ui.tasks[ui.currentIndex];
 for(const auto& t:ui.tasks)if(t.state=="running")return &t;
 for(const auto& t:ui.tasks)if(t.state=="unknown")return nullptr;
 for(const auto& t:ui.tasks)if(t.state=="done"&&ui.unread.contains(t.id))return &t;
 for(const auto& t:ui.tasks)if(t.state=="done")return &t;
 return &ui.tasks.front();
}

inline bool taskListRegion(int x,int y){return x>=16&&x<302&&y>=70&&y<232;}
inline int taskCardAt(const ListLayout& layout,float offset,int count,int x,int y){
 if(x<16||x>=layout.width-18||y<layout.rowsTop()||y>=layout.rowsBottom())return -1;
 int local=y-layout.rowsTop()+int(std::lround(offset));
 if(local<0)return -1;
 int index=local/TaskRow::height,inset=local%TaskRow::height;
 if(index>=count||inset<TaskRow::cardTop+2||inset>=TaskRow::cardTop+TaskRow::cardHeight-2)return -1;
 return index;
}
inline const Task* listTaskTarget(const UiState& ui,bool live,int x,int y){
 if(!live)return nullptr;
 int index=taskCardAt({320,240},ui.scroll.visualOffset(),int(ui.tasks.size()),x,y);
 return index>=0?&ui.tasks[index]:nullptr;
}
