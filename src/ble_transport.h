#pragma once
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>
#include <Preferences.h>
#include <atomic>
#include <esp_system.h>
#include <mbedtls/gcm.h>
#include <mbedtls/md.h>
#include "ble_frame.h"

// AES-256-GCM 应用层加密。每次连接随机挑战，HMAC 派生双向独立密钥，序号防重放。
// 绑定密钥只经本机 USB 写入 NVS；无线接口不提供绑定、运动或固件写入命令。
class BleTransport:public BLEServerCallbacks,public BLECharacteristicCallbacks {
 struct Chunk{uint32_t epoch;uint16_t size;uint8_t data[512];};
 QueueHandle_t queue=nullptr;
 BLEServer* server=nullptr;
 BLECharacteristic *rx=nullptr,*tx=nullptr,*identity=nullptr;
 std::atomic<uint32_t> epoch{0};
 std::atomic<bool> attached{false},restart{false};
 portMUX_TYPE mux=portMUX_INITIALIZER_UNLOCKED;
 uint8_t challenge[16]={},key[32]={},rxKey[32]={},txKey[32]={};
 uint32_t activeEpoch=0,rxSequence=0,txSequence=0;
 bool bound=false;
 BleFrame parser;
 void derive(const char* direction,uint8_t* out){
  uint8_t seed[17];portENTER_CRITICAL(&mux);memcpy(seed,challenge,16);portEXIT_CRITICAL(&mux);seed[16]=direction[0];
  mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),key,32,seed,sizeof(seed),out);
 }
 static uint32_t sequence(const uint8_t* p){return (uint32_t(p[0])<<24)|(uint32_t(p[1])<<16)|(uint32_t(p[2])<<8)|p[3];}
 static void seqBytes(uint32_t seq,uint8_t* p){p[0]=seq>>24;p[1]=seq>>16;p[2]=seq>>8;p[3]=seq;}
 void onConnect(BLEServer*)override{
  uint8_t nonce[16];esp_fill_random(nonce,sizeof(nonce));
  portENTER_CRITICAL(&mux);memcpy(challenge,nonce,16);portEXIT_CRITICAL(&mux);
  String hello="WG1\t"+deviceId+"\t";char hex[3];
  for(uint8_t b:nonce){snprintf(hex,sizeof(hex),"%02x",b);hello+=hex;}
  identity->setValue(hello.c_str());epoch.fetch_add(1);attached=true;
 }
 void onDisconnect(BLEServer*)override{attached=false;epoch.fetch_add(1);restart=true;}
 void onWrite(BLECharacteristic* characteristic)override{
  auto value=characteristic->getValue();
  if(value.empty()||value.size()>512)return;
  Chunk chunk;chunk.epoch=epoch.load();chunk.size=value.size();memcpy(chunk.data,value.data(),value.size());
  if(xQueueSend(queue,&chunk,0)!=pdTRUE){attached=false;server->disconnect(server->getConnId());}
 }
public:
 String deviceId;
 static constexpr const char* serviceUUID="45860001-3a86-4a23-b79b-9ce13700c681";
 bool provision(const String& hex){
  if(hex.length()!=64)return false;
  uint8_t fresh[32];
  for(int i=0;i<64;i++){char c=hex[i];int n=c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:-1;if(n<0)return false;if(i%2)fresh[i/2]|=n;else fresh[i/2]=n<<4;}
  Preferences prefs;if(!prefs.begin("weiguang",false))return false;
  bool saved=prefs.putBytes("ble_key",fresh,32)==32;prefs.end();if(!saved)return false;
  if(attached)server->disconnect(server->getConnId());
  memcpy(key,fresh,32);bound=true;epoch.fetch_add(1);parser.clear();return true;
 }
 void begin(){
  char id[13];snprintf(id,sizeof(id),"%012llx",(unsigned long long)ESP.getEfuseMac());deviceId=id;
  Preferences prefs;if(prefs.begin("weiguang",true)){bound=prefs.getBytesLength("ble_key")==32;if(bound)prefs.getBytes("ble_key",key,32);prefs.end();}
  queue=xQueueCreate(16,sizeof(Chunk));if(!queue){Serial.println("BLE\terror\tqueue");return;}
  BLEDevice::init(("Weiguang-"+deviceId.substring(8)).c_str());BLEDevice::setMTU(247);
  server=BLEDevice::createServer();server->setCallbacks(this);
  auto service=server->createService(serviceUUID);
  rx=service->createCharacteristic("45860002-3a86-4a23-b79b-9ce13700c681",BLECharacteristic::PROPERTY_WRITE);rx->setCallbacks(this);
  tx=service->createCharacteristic("45860003-3a86-4a23-b79b-9ce13700c681",BLECharacteristic::PROPERTY_NOTIFY);tx->addDescriptor(new BLE2902());
  identity=service->createCharacteristic("45860004-3a86-4a23-b79b-9ce13700c681",BLECharacteristic::PROPERTY_READ);
  identity->setValue(("WG1\t"+deviceId+"\t-").c_str());service->start();
  auto adv=server->getAdvertising();adv->addServiceUUID(serviceUUID);adv->setScanResponse(true);adv->start();
  Serial.printf("BLE\tready\tbound=%d\tid=%s\theap=%u\n",bound,deviceId.c_str(),ESP.getFreeHeap());
 }
 bool poll(std::string& plain){
  if(!queue)return false;
  if(restart.exchange(false))server->startAdvertising();
  uint32_t current=epoch.load();if(activeEpoch!=current){activeEpoch=current;rxSequence=txSequence=0;parser.clear();derive("M",rxKey);derive("R",txKey);}
  Chunk chunk;if(xQueueReceive(queue,&chunk,0)!=pdTRUE)return false;
  if(!bound||!attached||chunk.epoch!=activeEpoch)return false;
  std::string frame;if(!parser.append(chunk.data,chunk.size,millis(),frame))return false;
  const auto bytes=reinterpret_cast<const uint8_t*>(frame.data());uint32_t seq=sequence(bytes+5);
  if(seq==0||seq<=rxSequence)return false;
  uint8_t nonce[12]={};seqBytes(seq,nonce+8);size_t length=frame.size()-25;plain.resize(length);
  mbedtls_gcm_context ctx;mbedtls_gcm_init(&ctx);mbedtls_gcm_setkey(&ctx,MBEDTLS_CIPHER_ID_AES,rxKey,256);
  int ok=mbedtls_gcm_auth_decrypt(&ctx,length,nonce,12,bytes,9,bytes+9+length,16,bytes+9,reinterpret_cast<uint8_t*>(&plain[0]));mbedtls_gcm_free(&ctx);
  if(ok||epoch.load()!=activeEpoch){plain.clear();return false;}
  rxSequence=seq;return true;
 }
 void reply(const String& message){
  if(!attached||epoch.load()!=activeEpoch||!bound||message.length()>512||txSequence==UINT32_MAX)return;
  uint8_t frame[537],nonce[12]={};size_t length=message.length(),body=length+20;frame[0]='W';frame[1]='G';frame[2]=1;frame[3]=body>>8;frame[4]=body;
  seqBytes(++txSequence,frame+5);seqBytes(txSequence,nonce+8);
  mbedtls_gcm_context ctx;mbedtls_gcm_init(&ctx);mbedtls_gcm_setkey(&ctx,MBEDTLS_CIPHER_ID_AES,txKey,256);
  int ok=mbedtls_gcm_crypt_and_tag(&ctx,MBEDTLS_GCM_ENCRYPT,length,nonce,12,frame,9,reinterpret_cast<const uint8_t*>(message.c_str()),frame+9,16,frame+9+length);mbedtls_gcm_free(&ctx);
  if(ok)return;
  size_t chunk=std::min(size_t(180),size_t(std::max(23,int(server->getPeerMTU(server->getConnId())))-3));
  for(size_t at=0;at<length+25;at+=chunk){tx->setValue(frame+at,std::min(chunk,length+25-at));tx->notify();delay(5);}
 }
};
