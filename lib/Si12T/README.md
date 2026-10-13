# 独立摸头驱动

来自 M5Stack 官方 StackChan-BSP 的 Si12T 驱动，保留原 MIT 许可证；下载于 2026-10-08。仅编译 Si12T.h/cpp，不引入完整 BSP 的 begin、音频、Servo 或灯带初始化。

来源：https://github.com/m5stack/StackChan-BSP/tree/main/src/drivers/Si12T
归档 SHA-256：dca8179a764ee0aa6169a2d72c614b7683756d8ffd3d53e2ae18e327d7d7998e

传感器走 M5 内部 I2C，地址 0x68。配置与官方原厂保持一致：Low / Level 3（0x33），每 50ms 读取 0x10 的三组二位强度。每次读取检查成功与否；无法探测或配置失败时不生成摸头事件。
