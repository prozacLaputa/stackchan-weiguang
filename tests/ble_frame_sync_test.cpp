#include "../src/ble_frame.h"
#include "../src/sync_state.h"
#include <cassert>
#include <iostream>
int main(){
 std::string packet="WG";packet.push_back(1);packet.push_back(0);packet.push_back(24);packet.append(24,'x');
 for(size_t cut=1;cut<packet.size();cut++){
  BleFrame f;std::string out;
  assert(!f.append((const uint8_t*)packet.data(),cut,100,out));
  assert(f.append((const uint8_t*)packet.data()+cut,packet.size()-cut,101,out));assert(out==packet&&f.buffer.empty());
 }
 BleFrame f;std::string out;assert(!f.append((const uint8_t*)packet.data(),10,1,out));
 assert(!f.append((const uint8_t*)packet.data()+10,packet.size()-10,4000,out));assert(f.buffer.empty());
 std::string oversized="WG";oversized.push_back(1);oversized.push_back(char(255));oversized.push_back(char(255));
 assert(!f.append((const uint8_t*)oversized.data(),5,5000,out)&&f.buffer.empty());
 std::string huge(513,'x');assert(!f.append((const uint8_t*)huge.data(),huge.size(),6000,out));
 std::string garbage="WRONG";assert(!f.append((const uint8_t*)garbage.data(),garbage.size(),7000,out));
 assert(f.append((const uint8_t*)packet.data(),packet.size(),8000,out));
 SyncState sync;assert(!sync.live()&&std::string(sync.title())=="等待 Mac"&&sync.goodSeconds==-1);
 sync.accept(100,SyncTransport::ble,true,600,0);assert(sync.live()&&std::string(sync.title())=="蓝牙同步");
 sync.accept(200,SyncTransport::ble,false,600,3);assert(!sync.live()&&sync.linked&&std::string(sync.title())=="数据异常");
 sync.accept(1200,SyncTransport::ble,false,-1,0);assert(sync.goodSeconds==600);
 assert(sync.age(2200)==5&&!sync.expire(16200));assert(sync.expire(16201)&&!sync.linked&&sync.goodSeconds==600);
 sync.accept(16000,SyncTransport::usb,true,620,0);assert(sync.live()&&std::string(sync.title())=="USB 同步");
 sync.accept(UINT32_MAX-1000,SyncTransport::ble,true,621,0);assert(!sync.expire(13999)&&sync.expire(14000));
 std::cout<<"BLE fragmentation, bounds, timeout, recovery and sync freshness passed\n";
}
