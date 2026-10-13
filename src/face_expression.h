#pragma once
#include <algorithm>
#include <stdint.h>
#include <string>

// 此模块只输出屏幕姿态，不引用任何电机或音频接口。
enum class FaceMood { idle,focus,thinking,curious,joy,waiting,shy,content,rest };
inline const char* faceName(FaceMood m){
 switch(m){case FaceMood::focus:return "focus";case FaceMood::thinking:return "thinking";
 case FaceMood::curious:return "curious";case FaceMood::joy:return "joy";
 case FaceMood::waiting:return "waiting";case FaceMood::shy:return "shy";
 case FaceMood::content:return "content";case FaceMood::rest:return "rest";default:return "idle";}
}
inline bool knownExpression(const std::string& s){return s=="idle"||s=="focus"||s=="thinking"||s=="curious"||s=="joy";}
inline FaceMood selectFace(bool connected,bool pet,bool waiting,bool completed,const std::string& mood){
 if(pet)return FaceMood::shy;
 if(!connected)return FaceMood::idle;
 if(waiting)return FaceMood::waiting;
 if(completed)return FaceMood::joy;
 if(mood=="focus")return FaceMood::focus;
 if(mood=="thinking")return FaceMood::thinking;
 if(mood=="curious")return FaceMood::curious;
 if(mood=="joy")return FaceMood::joy;
 return FaceMood::idle;
}
struct FacePose {
 float eyeWidth,eyeHeight,eyeCurve,leftLift,rightLift,brow,mouthWidth,mouthCurve,mouthOpen,cheek,dots;
};
inline FacePose poseFor(FaceMood m){
 switch(m){
 case FaceMood::focus:   return {12,4,0,0,0,0,19,2,0,0,0};
 case FaceMood::thinking:return {10,7,2,-3,-3,0,17,2,0,0,1};
 case FaceMood::curious: return {10,9,0,-3,2,1,5,0,4,0,0};
 case FaceMood::waiting: return {11,2,1,0,0,0,19,3,0,0,0};
 case FaceMood::joy:     return {12,2,7,0,0,0,23,6,0,0,0};
 case FaceMood::shy:     return {12,2,7,0,0,0,23,6,0,1,0};
 case FaceMood::content: return {12,1.5,4,1,1,0,17,5,0,.45,0};
 case FaceMood::rest:    return {12,1,-4,2,2,0,20,3,0,0,0};
 default:               return {10,10,0,0,0,0,30,4,0,0,0};
 }
}
inline FacePose mixPose(const FacePose& a,const FacePose& b,float t){
 FacePose out;
 #define FACE_MIX(field) out.field=a.field+(b.field-a.field)*t
 FACE_MIX(eyeWidth);FACE_MIX(eyeHeight);FACE_MIX(eyeCurve);FACE_MIX(leftLift);FACE_MIX(rightLift);
 FACE_MIX(brow);FACE_MIX(mouthWidth);FACE_MIX(mouthCurve);FACE_MIX(mouthOpen);FACE_MIX(cheek);FACE_MIX(dots);
 #undef FACE_MIX
 return out;
}
class FaceAnimator {
 FacePose from=poseFor(FaceMood::idle),to=from;
 uint32_t since=0,duration=380;
public:
 FaceMood mood=FaceMood::idle;
 FacePose pose(uint32_t now)const{
  float t=std::min(1.0f,uint32_t(now-since)/float(duration));return mixPose(from,to,t*t*(3-2*t));
 }
 FacePose update(FaceMood next,uint32_t now){
  if(next!=mood){from=pose(now);to=poseFor(next);since=now;duration=next==FaceMood::rest?1000:380;mood=next;}
  return pose(now);
 }
};
