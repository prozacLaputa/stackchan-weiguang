#include "focus_dial.h"
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <vector>
struct Canvas {
 std::vector<uint16_t> pixels=std::vector<uint16_t>(320*240);
 void drawPixel(int x,int y,uint16_t c){if(x>=0&&x<320&&y>=0&&y<240)pixels[y*320+x]=c;}
};
int main(int argc,char** argv){
 if(argc<5)return 1;
 Canvas c;auto seconds=std::strtoul(argv[1],nullptr,10);float remaining=std::strtof(argv[2],nullptr);bool compact=std::atoi(argv[3]);
 FocusDial::ring(c,remaining,compact,false);FocusDial::digits(c,seconds,compact?108:120,compact,seconds==0);
 std::ofstream out(argv[4],std::ios::binary);out<<"P6\n320 240\n255\n";
 for(auto p:c.pixels){unsigned char rgb[]={static_cast<unsigned char>((p>>11)*255/31),static_cast<unsigned char>(((p>>5)&63)*255/63),static_cast<unsigned char>((p&31)*255/31)};out.write(reinterpret_cast<char*>(rgb),3);}
}
