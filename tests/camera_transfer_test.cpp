#include "camera_transfer.h"
#include <algorithm>
#include <cassert>
#include <vector>
int main(){
 // Actual call pattern: slow UI frames can leave 150ms between camera ticks.
 // A 12KB JPEG must finish inside the existing 3-second receiver deadline.
 int remaining=12000;uint32_t now=0;std::vector<int> batches;
 for(;remaining&&now<3000;now+=150){
  int room=4096,sent=0;
  pumpCameraChunks([&]{return room;},[&]{
   if(!remaining)return false;remaining-=std::min(384,remaining);room-=540;++sent;return remaining>0;
  },[&]{return now;});
  batches.push_back(sent);
 }
 assert(remaining==0&&now<3000);
 for(int count:batches)assert(count<=6);
 // Back pressure must never enter a potentially blocking send.
 int writes=0;pumpCameraChunks([]{return 639;},[&]{++writes;return true;},[]{return 0u;});assert(writes==0);
 // Slow writes yield after 3ms even if there is still buffer space.
 now=0;pumpCameraChunks([]{return 4096;},[&]{++writes;now+=2;return true;},[&]{return now;});assert(writes==2);
 // End of the frame is final: no duplicate tail or empty chunk.
 writes=0;pumpCameraChunks([]{return 4096;},[&]{++writes;return false;},[]{return 0u;});assert(writes==1);
}
