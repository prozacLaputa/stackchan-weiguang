#include "../src/remote_settings.h"
#include <cassert>
#include <iostream>
int main(){
 DeviceSettings settings;auto original=settings.packed();
 assert(!patchDeviceSettings(settings,"2","9","0")&&settings.packed()==original);
 for(const char* bad:{"","12","-1","x","1\t"," 1"})assert(!patchDeviceSettings(settings,bad,"-","-")&&settings.packed()==original);
 assert(!patchDeviceSettings(settings,"-","-","-"));
 assert(patchDeviceSettings(settings,"2","-","-")&&settings.light==2&&settings.rest==1&&settings.petMotion);
 settings.rest=4; // 在设备触屏修改后，Mac 只改亮度不能覆盖它。
 assert(patchDeviceSettings(settings,"0","-","0")&&settings.light==0&&settings.rest==4&&!settings.petMotion);
 assert(patchDeviceSettings(settings,"3","0","1")&&settings.light==3&&settings.rest==0&&settings.petMotion);
 assert(patchDeviceSettings(settings,"-","-","-","1","0")&&settings.waitMotion&&!settings.doneMotion&&settings.petMotion);
 auto enabled=settings.packed();
 assert(!patchDeviceSettings(settings,"1","1","0","0","2")&&settings.packed()==enabled);
 assert(!patchDeviceSettings(settings,"-","-","-","1","")&&settings.packed()==enabled);
 assert(patchDeviceSettings(settings,"1","-","0")&&settings.waitMotion&&!settings.doneMotion&&!settings.petMotion);
 std::cout<<"Remote settings: atomic validation and concurrent local-setting preservation passed\n";
}
