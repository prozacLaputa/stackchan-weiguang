#include "../src/face_expression.h"
#include <cassert>
#include <cmath>
#include <iostream>
int main(){
 assert(selectFace(true,false,false,false,"focus")==FaceMood::focus);
 assert(selectFace(true,false,true,true,"joy")==FaceMood::waiting);
 assert(selectFace(true,true,true,true,"curious")==FaceMood::shy);
 assert(selectFace(false,false,true,true,"joy")==FaceMood::idle);
 assert(selectFace(false,true,false,false,"focus")==FaceMood::shy);
 assert(selectFace(true,false,false,true,"curious")==FaceMood::joy);
 assert(selectFace(true,false,false,false,"invalid")==FaceMood::idle);
 for(const auto& s:{"idle","focus","thinking","curious","joy"})assert(knownExpression(s));
 assert(!knownExpression("MOTION_ON")&&!knownExpression("shy"));
 FaceAnimator a;auto idle=a.pose(1000);auto start=a.update(FaceMood::focus,1000);
 assert(start.eyeHeight==idle.eyeHeight&&start.mouthWidth==30);
 auto middle=a.update(FaceMood::focus,1190);assert(std::abs(middle.eyeHeight-7)<.001f);
 auto end=a.update(FaceMood::focus,1380);assert(end.eyeHeight==4&&end.mouthWidth==19);
 auto interrupted=a.update(FaceMood::joy,1450);assert(interrupted.eyeHeight==4);
 auto partial=a.pose(1600);auto retarget=a.update(FaceMood::waiting,1600);
 assert(std::abs(partial.eyeCurve-retarget.eyeCurve)<.001f);
 assert(a.update(FaceMood::waiting,1980).mouthOpen==0);
 auto waiting=poseFor(FaceMood::waiting);assert(waiting.brow==0&&waiting.eyeHeight<=2&&waiting.mouthCurve>0);
 FaceAnimator wrap;wrap.update(FaceMood::thinking,UINT32_MAX-100);
 assert(wrap.update(FaceMood::thinking,300).dots==1);
 for(auto m:{FaceMood::idle,FaceMood::focus,FaceMood::thinking,FaceMood::curious,FaceMood::joy,FaceMood::waiting,FaceMood::shy}){
  auto p=poseFor(m);assert(p.eyeWidth<=12&&p.eyeHeight<=10&&p.mouthWidth<=30);
 }
 std::cout<<"Expression priority, bounded geometry, smooth retargeting and clock wrap passed\n";
}
