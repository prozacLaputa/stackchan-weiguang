# 第三方来源

Updated-At: 2026-10-08
Updated-By: Codex
Profile: Execution
Reason: 记录原厂表情、触摸驱动和接近通道待机配置来源

- `lib/Si12T/Si12T.h` 和 `.cpp` 来自 [M5Stack StackChan-BSP](https://github.com/m5stack/StackChan-BSP/tree/main/src/drivers/Si12T)，原样保留；MIT 许可证见 `lib/Si12T/LICENSE`。
- `src/main.cpp` 的原厂风格表情独立重绘于 Canvas，参考 [StackChan 默认眼睛/嘴巴](https://github.com/m5stack/StackChan/tree/main/firmware/main/stackchan/avatar/skins/default) 与 [shy.cpp](https://github.com/m5stack/StackChan/blob/main/firmware/main/stackchan/avatar/decorators/shy.cpp) 的位置、比例和颜色。参考源版权：2026 M5Stack Technology CO LTD，MIT。许可证文本同时收录于 `lib/Si12T/LICENSE`。
- v0.14 的 `lib/FTServo/` 仅收录 BSP 内 FTServo_Arduino 的 SCSCL、SCS、SCSerial 和 INST 文件，版权 2024 ftservo，MIT 许可证见该目录 LICENSE；`SCSerial.cpp` 增加 ESP-IDF 4 / 5 时钟枚举兼容分支，ESP32-S3 旧版使用 XTAL 时钟。
- `lib/PY32IOExpander/` 为同一 BSP 的电源扩展驱动，原样复制，MIT 许可证见该目录 LICENSE。只操作舵机供电引脚，不启用灯效。
- `src/quiet_motion.h` 独立管理受限小动作，参考 [官方 BSP 舵机接口](https://github.com/m5stack/StackChan-BSP/blob/main/src/M5StackChan.cpp) 的总线、只读原厂校准值与位置映射；不导入完整原厂 HAL、语音、摄像头、自动归位或校准写入。
- v0.15 抚摸动作参考 [原厂 head_pet.h](https://github.com/m5stack/StackChan/blob/main/firmware/main/stackchan/modifiers/head_pet.h) 的抬头幅度，独立实现限位往返与平滑曲线，不复制随机动作或全局动作系统。
- v0.15 的独立接近驱动已于 v0.17 删除，仅在 `src/main.cpp` 保留接近通道待机写入和只读确认。寄存器依据 [Lite-On LTR-553ALS-WA 数据手册](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/core/K128%20CoreS3/LTR-553ALS-WA.PDF) 和 [M5Stack M5CoreS3 LTR5XX](https://github.com/m5stack/M5CoreS3/blob/main/src/utility/LTR5XX.cpp) / [官方示例](https://github.com/m5stack/M5CoreS3/blob/main/examples/Basic/ltr553/ltr553.ino)。未引入整个已弃用的 M5CoreS3 库。

下载快照校验与来源路径见 README 和 lib/Si12T/README.md；源码下载缓存留在 Git 忽略的 `.vendor/factory-reference/`。

- 日常同步使用 pyserial 3.5；离线 wheel 来自 PyPI 官方分发，BSD 许可证从同版本官方源码包提取，保存在 `bridge/wheels/pyserial-3.5-LICENSE.txt`，随迁移包和安装副本保留。文件 SHA-256 为 `c4451db6ba391ca6ca299fb3ec7bae67a5c55dde170964c7a14ceefec02f2cf0`，安装前重新校验；没有修改包内容。

- 音乐陪伴通过外部命令行工具 [media-control](https://github.com/ungive/media-control) 读取 macOS 媒体状态和发送播放控制，使用 [Homebrew 分发](https://formulae.brew.sh/formula/media-control) 单独安装，不复制其源码或二进制进本项目。它依赖非公开媒体接口，系统更新后需要重新验证。仅接受 QQ 音乐与网易云音乐来源；不读取账号、Cookie、音频或封面。


- 可选语音依赖 `certifi`、`cryptography`（Python）和系统安装的 `ffmpeg`／`libopus`；不把这些工具、系统音色或原厂身份打包进仓库。解析和传输代码参考 [XiaoZhi ESP32 协议](https://github.com/78/xiaozhi-esp32) 与 [M5Stack StackChan](https://github.com/m5stack/StackChan) 公开实现独立编写。原厂云服务、角色与音色按各自条款使用，不属于本项目 MIT 许可的资产。
- 本地视觉使用 macOS Apple Vision 与 Arduino-ESP32 随附的摄像头支持；不打包额外识别模型或保存图像。
