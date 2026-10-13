// 直接编译实际 M5Unified 触摸状态机，仅用测试输入代替 I2C 坐标来源。
#define M5UNIFIED_IMPLEMENTATION
#include "../.pio/libdeps/stackchan/M5Unified/src/utility/Touch_Class.inl"
#include "../src/touch_gesture.h"
#include <cassert>
#include <iostream>
int main(){
 m5gfx::LGFX_Device panel;
 auto delta=[&](int threshold){
  m5::Touch_Class touch{};touch.begin(&panel);touch.setFlickThresh(threshold);
  panel.pressed=true;panel.point.x=150;panel.point.y=180;touch.update(100);
  TouchGesture gesture;auto first=touch.getDetail();gesture.begin(first.x,first.y,100);
  panel.point.y=175;touch.update(116);auto second=touch.getDetail();return gesture.move(second.x,second.y);
 };
 std::cout<<"5px raw finger movement: default threshold = "<<delta(8)<<", low threshold = "<<delta(0)<<"\n";
 assert(delta(0)==-5);
}
