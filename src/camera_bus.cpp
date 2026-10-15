#include <M5Unified.h>

// GC0308 shares the board's I2C controller with touch/power/head sensing.
// Route SCCB through its existing owner; never release/reinstall that bus.
// Signatures match the bundled esp32-camera ABI (Arduino ESP32 2.0.17).
extern "C" {
int __wrap_SCCB_Init(int, int) { return 0; }
int __wrap_SCCB_Use_Port(int) { return 0; }
int __wrap_SCCB_Deinit() { return 0; }
uint8_t __wrap_SCCB_Probe() {
 uint8_t id=0;
 return M5.In_I2C.readRegister(0x21,0,&id,1,100000)&&id==0x9b ? 0x21:0;
}
uint8_t __wrap_SCCB_Read(uint8_t address,uint8_t reg) {
 uint8_t value=0xff;
 if(address==0x21)M5.In_I2C.readRegister(address,reg,&value,1,100000);
 return value;
}
int __wrap_SCCB_Write(uint8_t address,uint8_t reg,uint8_t value) {
 return address==0x21&&M5.In_I2C.writeRegister8(address,reg,value,100000)?0:-1;
}
// This board has only the 8-bit-register GC0308; other sensor probes fail closed.
uint8_t __wrap_SCCB_Read16(uint8_t,uint16_t) {return 0xff;}
int __wrap_SCCB_Write16(uint8_t,uint16_t,uint8_t) {return -1;}
uint16_t __wrap_SCCB_Read_Addr16_Val16(uint8_t,uint16_t) {return 0xffff;}
int __wrap_SCCB_Write_Addr16_Val16(uint8_t,uint16_t,uint16_t) {return -1;}
}
