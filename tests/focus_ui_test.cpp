#include "focus_ui.h"
#include "desktop_actions.h"
#include "desk_companion.h"
#include "remote_settings.h"
#include <cassert>
#include <iostream>
int main(){
 FocusPresentation ui;
 assert(ui.controls(100,false)&&!ui.controls(100,true));
 ui.reveal(100);assert(ui.controls(4599,true)&&!ui.controls(4600,true));
 ui.hide();assert(!ui.controls(110,true));ui.reveal(UINT32_MAX-999);assert(ui.controls(2000,true)&&!ui.controls(3500,true));
 assert(homeFocusEntry(250,45)&&!waitingRegion(250,45));
 assert(waitingRegion(13,143)&&waitingRegion(307,235)&&!waitingRegion(10,200));
 assert(FocusLayout::hit(50,210,true)==FocusHit::back);
 assert(FocusLayout::hit(150,210,true)==FocusHit::primary);
 assert(FocusLayout::hit(280,210,true)==FocusHit::stop);
 assert(FocusLayout::hit(150,155,true)==FocusHit::none&&FocusLayout::hit(150,155,false)==FocusHit::motion);
 assert(FocusLayout::hit(30,40,true)==FocusHit::none&&FocusLayout::hit(30,40,false)==FocusHit::shorter);
 // v4 -> v5 preserves all existing settings; the specifically requested new motion starts on.
 DeviceSettings s;assert(s.load(0x5704EB15u));assert(s.focusMotion&&s.skin==1&&s.light==1);
 auto old=s;assert(patchDeviceSettings(s,"-","-","-","-","-","-","-","-","-","-","0"));
 assert(!s.focusMotion&&s.skin==old.skin&&s.daily==old.daily&&s.waitMotion==old.waitMotion&&s.doneMotion==old.doneMotion);
 DeviceSettings restored;assert(restored.load(s.packed())&&!restored.focusMotion&&restored.packed()==s.packed());
 auto before=s.packed();assert(!patchDeviceSettings(s,"2","-","-","-","-","-","-","-","-","-","2")&&s.packed()==before);
 assert(!s.load(0x57050080u)&&s.packed()==before);
 FocusTimer timer;timer.start(60,10);assert(timer.completions==0);timer.tick(60010);assert(timer.completions==1);
 timer.tick(60100);timer.tick(70000);assert(timer.completions==1);timer.stop();timer.start(60,80000);timer.pause(90000);
 timer.tick(150000);assert(timer.completions==1);timer.resume(150001);timer.tick(200001);assert(timer.completions==2);
 std::cout<<"Immersive reveal/timeout, entry hit regions, preference migration and one-shot finish passed\n";
}
