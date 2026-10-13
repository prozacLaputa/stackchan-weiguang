#pragma once
#include "SCSCL.h"
class Preferences {
public:
 bool begin(const char*,bool readOnly){return readOnly;}
 int getInt(const char*,int){return fake.zero;}
 void end(){}
};
