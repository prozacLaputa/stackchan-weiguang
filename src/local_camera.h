#pragma once
#include <Arduino.h>
#include <esp_camera.h>
#include <img_converters.h>
#include <atomic>
#include <mbedtls/base64.h>
#include "camera_transfer.h"

// USB-only, explicit start, five-second lease, one frame in flight.
// Capture/JPEG conversion happens off the UI thread; USB writes are bounded.
class LocalCamera {
 enum Job {idle,capture,ready};
 std::atomic<int> job{idle};
 uint8_t* jpeg=nullptr;size_t length=0,offset=0;
 bool started=false,stopping=false,header=false;
 uint32_t renewed=0,sentAt=0,seq=0;
 TaskHandle_t worker=nullptr;
 static void run(void* context){
  auto self=static_cast<LocalCamera*>(context);
  for(;;){
   if(self->job.load()==capture){
    auto fb=esp_camera_fb_get();
    if(fb){
     if(!fmt2jpg(fb->buf,fb->len,fb->width,fb->height,fb->format,72,&self->jpeg,&self->length))self->length=0;
     esp_camera_fb_return(fb);
    }
    self->job.store(ready);
   }
   vTaskDelay(pdMS_TO_TICKS(5));
  }
 }
 void discard(){if(jpeg){free(jpeg);jpeg=nullptr;}length=offset=0;header=false;job.store(idle);}
public:
 bool active()const{return started&&!stopping;}
 bool busy()const{return job.load()!=idle;}
 bool begin(uint32_t now){
  if(stopping)return false;
  if(started){renewed=now;return true;}
  camera_config_t c={};c.pin_pwdn=-1;c.pin_reset=-1;c.pin_xclk=-1;
  c.pin_sccb_sda=-1;c.pin_sccb_scl=-1;c.sccb_i2c_port=0;
  c.pin_d7=47;c.pin_d6=48;c.pin_d5=16;c.pin_d4=15;
  c.pin_d3=42;c.pin_d2=41;c.pin_d1=40;c.pin_d0=39;
  c.pin_vsync=46;c.pin_href=38;c.pin_pclk=45;
  c.xclk_freq_hz=20000000;c.ledc_timer=LEDC_TIMER_0;c.ledc_channel=LEDC_CHANNEL_0;
  c.pixel_format=PIXFORMAT_RGB565;c.frame_size=FRAMESIZE_QVGA;
  c.jpeg_quality=12;c.fb_count=2;c.fb_location=CAMERA_FB_IN_PSRAM;c.grab_mode=CAMERA_GRAB_LATEST;
  if(esp_camera_init(&c)!=ESP_OK)return false;
  if(!worker&&xTaskCreatePinnedToCore(run,"local-camera",6144,this,1,&worker,0)!=pdPASS){esp_camera_deinit();return false;}
  started=true;renewed=now;return true;
 }
 bool request(uint32_t id,uint32_t now){
  if(!active()||busy())return false;
  renewed=sentAt=now;seq=id;job.store(capture);return true;
 }
 void stop(){if(started)stopping=true;}
 void tick(uint32_t now){
  if(!started)return;
  if(uint32_t(now-renewed)>5000||!Serial)stopping=true;
  if(stopping){
   if(job.load()==capture)return;
   discard();esp_camera_deinit();started=stopping=false;return;
  }
  if(job.load()!=ready)return;
  if(!length||length>65536){discard();Serial.println("CAM_ERROR\tframe");return;}
  if(uint32_t(now-sentAt)>3500){stop();return;}
  if(!header){Serial.printf("CAM_FRAME\t%u\t%u\n",seq,unsigned(length));header=true;}
  // Complete bounded lines: touch/motor diagnostics may safely interleave.
  // Seq + offset reject truncation, duplication, or frames from another request.
  pumpCameraChunks([]{return Serial.availableForWrite();},[&]{
   size_t n=std::min(length-offset,size_t(384)),encoded=0;unsigned char data[520];
   mbedtls_base64_encode(data,sizeof(data),&encoded,jpeg+offset,n);data[encoded]=0;
   Serial.printf("CAM_DATA\t%u\t%u\t%s\n",seq,unsigned(offset),data);offset+=n;
   return offset<length;
  },[]{return millis();});
  if(offset==length)discard();
 }
};
