#pragma once
#include "SCSCL.h"
namespace m5 {class PY32IOExpander_Class {
public:
 enum Pull {pull_up};
 bool begin(){return fake.clock>=fake.ioReadyAt;}bool setDirection(int,bool){return true;}
 bool setPullMode(int,Pull){return true;}bool digitalWrite(int,bool on){fake.powered=on;return true;}
};}
