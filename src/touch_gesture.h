#pragma once
#include "list_reading.h"
#include <stdint.h>
#include <algorithm>
#include <cstdlib>

enum class Hit { none, back };
struct ListLayout {
    int width,height;
    int rowsTop() const { return 70; }
    int rowsBottom() const { return height-8; }
    int viewportHeight() const { return rowsBottom()-rowsTop(); }
    int rowHeight() const { return TaskRow::height; }
    bool inRows(int x,int y) const { return x>=0&&x<width&&y>=rowsTop()-6&&y<height; }
    Hit hit(int x,int y) const {
        if(x<12||x>=width-12)return Hit::none;
        if(y>=28&&y<64){if(x<96)return Hit::back;return Hit::none;}
        // 任务行只是信息展示区，没有点击操作。
        return Hit::none;
    }
};
enum class Axis { pending, horizontal, vertical };
struct GestureResult { bool tap; int dragY; GestureResult(bool t=false,int dy=0):tap(t),dragY(dy){} };
struct TouchGesture {
    bool active=false;int startX=0,startY=0,lastY=0,maxTravel=0;uint32_t startAt=0;
    Axis axis=Axis::pending;bool scrollEnabled=true;
    void begin(int x,int y,uint32_t now,bool scroll=true){active=true;startX=x;startY=lastY=y;maxTravel=0;startAt=now;axis=Axis::pending;scrollEnabled=scroll;}
    int move(int x,int y){
        if(!active)return 0;
        int dx=x-startX,dy=y-startY;
        maxTravel=std::max(maxTravel,std::max(std::abs(dx),std::abs(dy)));
        // 只有纵向滚动，不把一次横向抖动永久锁死；斜划或随后转向仍可起滑。
        if(scrollEnabled&&axis!=Axis::vertical&&std::abs(dy)>=4&&std::abs(dy)*2>=std::abs(dx))axis=Axis::vertical;
        else if(axis==Axis::pending&&maxTravel>8)axis=Axis::horizontal;
        if(axis!=Axis::vertical)return 0;
        int delta=y-lastY;lastY=y;return delta;
    }
    GestureResult release(int x,int y,uint32_t now){
        if(!active)return {};
        int delta=move(x,y);active=false;
        // 滑动意图一旦出现，就不能在抬手时退化成点选；长按也不当轻点。
        return {axis==Axis::pending&&maxTravel<=8&&uint32_t(now-startAt)<600,delta};
    }
};
