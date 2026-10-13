#pragma once
#include <cstdint>
#include <cstring>
#include <cstdlib>
namespace m5gfx {
struct touch_point_t { int16_t x=0,y=0;uint8_t id=0,size=0; };
struct LGFX_Device {
 touch_point_t point;bool pressed=false;
 size_t getTouchRaw(touch_point_t* out,size_t){if(!pressed)return 0;*out=point;return 1;}
 void convertRawXY(touch_point_t*,size_t){}
};
}
