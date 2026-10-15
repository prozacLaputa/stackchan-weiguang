#include "../src/visual_face.h"
#include <cassert>
int main(){
 VisualFace face;assert(!face.active(0));
 assert(face.accept(100,-100,1,100));assert(face.smile(101));
 face.animate(180);assert(face.x>0&&face.x<32&&face.y<0&&face.y>-14);
 face.animate(350);assert(face.x==32&&face.y==-14);
 assert(!face.accept(101,0,0,1000));assert(!face.accept(0,0,3,1000));
 assert(!face.active(1900));assert(!face.smile(1900));
 face.accept(0,0,0,2000);assert(face.active(2000));
 face.clear();assert(!face.active(2000));assert(!face.smile(2000));
 face.accept(0,0,1,0xfffffff0);assert(face.active(100));assert(!face.active(1900));
 // A real welcome/celebration can occupy the face for six seconds while
 // camera gaze packets keep arriving. The greeting must survive that wait.
 VisualFace delayed;delayed.accept(-40,30,1,100);
 assert(!delayed.showing(100)&&delayed.pending);
 for(uint32_t now=500;now<=6500;now+=500)delayed.accept(-40,30,0,now);
 assert(delayed.smile(6500));
 for(uint32_t now=7000;now<9000;now+=500)delayed.accept(0,0,0,now);
 delayed.accept(0,0,0,9000);assert(delayed.smile(9000));
 delayed.accept(0,0,0,9500);assert(delayed.smile(9500));
 delayed.accept(0,0,0,10500);assert(!delayed.smile(10500));
 VisualFace expired;expired.accept(0,0,1,0);
 expired.accept(0,0,0,8500);assert(!expired.smile(8500));
 VisualFace lost;lost.accept(0,0,1,0);lost.clear();
 lost.accept(0,0,0,500);assert(!lost.smile(500));
 // Leases clear stale smiles as well as tracking; a new packet can't replay one.
 VisualFace lease;lease.accept(0,0,1,0);lease.accept(0,0,0,2000);
 assert(!lease.smile(2000));
 VisualFace wave;wave.accept(0,0,2,0);assert(wave.smile(0));
 auto pose=wave.response(poseFor(FaceMood::idle),500);
 assert(pose.cheek>.7f&&pose.eyeCurve>=7);assert(wave.waveOffset(500)>0);
 for(uint32_t now=0;now<4000;now+=65){
  wave.accept(100,-100,0,now);wave.animate(now);
  assert(wave.x<=32&&wave.y>=-14&&std::fabs(wave.waveOffset(now))<=6);
 }
 assert(!wave.showing(4000));
}
