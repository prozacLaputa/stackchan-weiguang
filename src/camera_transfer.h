#pragma once
#include <cstdint>

// Bound both bytes and CPU time so transport cannot monopolize the touch/motor loop.
template<class Available,class Send,class Clock>
void pumpCameraChunks(Available available,Send send,Clock clock){
    const uint32_t started=clock();
    for(int chunk=0;chunk<6&&uint32_t(clock()-started)<3;chunk++){
        if(available()<640||!send())break;
    }
}
