# 微光 · Weiguang

![Hardware](https://img.shields.io/badge/hardware-StackChan_K151-black)
![macOS](https://img.shields.io/badge/macOS-12%2B-black)
![License](https://img.shields.io/badge/license-MIT-green)

简体中文 | [English](README_EN.md)

让桌上的 StackChan 陪你写代码、专注和听歌。任务需要回应时看一眼，戴上 AirPods 后，还可以和它聊几句。

微光包含机器人固件、Mac 本地同步桥接和原生控制台。任务同步走 USB 或蓝牙，不需要机器人连 Wi-Fi；番茄钟、便签、音乐状态和本地视觉不调用云端模型。**可选语音使用原厂云服务，需要 Mac 联网及你自己的有效设备身份；它不使用 Codex 订阅，费用与长期额度尚未确认。** 本项目与 M5Stack、OpenAI 无隶属关系。

**v0.47 实验开发版 · 2026-10-15 更新。** 本次发布源码与文档，不提供签名、公证的 Mac 安装包或预编译固件。QQ 音乐的设备显示与暂停／播放已实机确认；网易云及工作接力的自然返回体验仍待验收。

## 看一眼

<img src="docs/screenshots/robot-note.png" width="480" alt="真实设备的猫系表情和暖黄色便签" />

真实设备帧缓冲：猫系表情与示例便签，不是效果图。以下截图来自 v0.46，展示保留的基础界面；新版控制台已改为分组页签，不把旧截图当成新版全貌。

<details>
<summary>番茄钟准备页与旧版 Mac 控制台</summary>

<img src="docs/screenshots/robot-focus-ready.png" width="480" alt="真实设备番茄钟准备页" />
<img src="docs/screenshots/mac-console.png" width="620" alt="v0.46 Mac 控制台窗口" />

</details>

另附[实际绘图代码生成的番茄钟预览](docs/preview/focus.png)，使用示例时间，属于渲染预览。

## 能做什么

| 功能 | 日常体验 |
| --- | --- |
| 任务与工作接力 | 最近活跃 Top8、运行／待回应／本轮结束、进展摘录；锁屏离开至少 30 秒后返回，查看仍待回应和可靠观察到的新结果 |
| 安静提醒 | 琥珀色提示、表情变化；按住待回应卡片约 0.9 秒立即打开对应 Codex 对话，不用松手 |
| 猫系陪伴 | 默认／猫系切换，摸头害羞与可选轻点头，慢眨眼、哈欠、闭眼休息；休息保持设定亮度 |
| 番茄钟与便签 | 15／25／45 分钟细线圆环、五分钟休息、今日小结；暖黄色便签，最多 32 字，设备保存 |
| 音乐陪伴 | QQ／网易云的歌名、歌手、进度与上一首／暂停播放／下一首；小脸在屏幕里轻晃，电机不动 |
| AirPods 语音 | 原厂音色、流式回复、连续对话与打断、聊天气泡、精简浮窗；可选连接问候与任务完成播报 |
| 语音操作 | 在主动进入的语音模式中，开始／暂停／继续／结束番茄钟，或者说一句便签 |
| 本地视觉（实验） | Chan 摄像头经 USB 交给 Mac Apple Vision，微笑、屏幕视线与挥手回应；不保存或上传画面，没有物理头部跟随 |
| 原生控制台 | 工作台／机器人／对话／连接分组，外观预览、可展开设置、保存反馈和两端同步 |

语音只在已绑定 AirPods 成为实际声音输出时播放；输出切换、断连或无法确认就停止，不回退到 Mac 或机器人扬声器。原厂音色由各自绑定角色决定，开发设备试听确认的是「湾湾小何v2」，仓库不分发该音色或服务账号。

## 开始之前

开发目标为 **M5Stack StackChan K151（CoreS3 / ESP32-S3、16 MB Flash）与 macOS 12+**。当前实测 Mac 为 macOS 15.6.1；新功能及外部音乐工具不保证覆盖所有旧系统。需要 Python 3.9+、Xcode Command Line Tools、PlatformIO 与 USB 数据线。控制台主要使用中文。

本项目替换原厂应用，不保留原厂菜单。**首次刷写前保存自己的完整工厂 Flash、分区表和校准数据，勿使用他人的整片备份。** 语音是 Mac 上的可选实验接入，不意味着所有原厂服务都可复用。

### 1. 构建

```sh
python3 -m venv .venv
.venv/bin/python -m pip install platformio==6.2.0
.venv/bin/python -m pip install --no-index --require-hashes -r bridge/requirements.txt --find-links bridge/wheels
.venv/bin/pio run
python3 macos/build.py
python3 macos/build_icon.py
python3 macos/build_panel.py
```

首次构建下载固定版本依赖。Swift 脚本生成 Apple Silicon／Intel 通用开发二进制并本机临时签名，不等同于公证发行包。详见[开发说明](docs/DEVELOPMENT.md)。

### 2. 备份与刷写

先读[硬件与刷写边界](docs/HARDWARE.md)。镜像位于 `.pio/build/stackchan/firmware.bin`；已验证设备仅更新 `0x10000` 应用分区，保留 NVS／校准。**不要将 PlatformIO 全套 upload 或 erase_flash 当作通用安装步骤。** 分区不同须先核对，本仓库不提供一键刷机。

### 3. 安装 Mac 同步

兼容固件已刷入、USB 已连接后：

```sh
./weiguang install
./weiguang status
./weiguang panel
./weiguang bind-bluetooth
```

允许「微光蓝牙」的系统蓝牙权限。安装为当前用户的登录服务，无需 sudo。一次 USB 绑定后可日常使用蓝牙；视觉采集仍需 USB。

### 4. 按需开启新功能

- **音乐**：`brew install media-control`，在「工作台 → 桌边陪伴」开启音乐陪伴。播放控制要求 AirPods 当前输出；音乐自身路由由 QQ／网易云及 macOS 管理。
- **工作接力**：同一位置独立开关，默认开启；有内容时机器人主屏出现「接力」。睡眠可能漏掉过程，界面会说明，不把推测当记录。
- **语音**：先按 [AirPods 语音设置](HEADPHONES_VOICE_SETUP.md) 准备自己的备份、依赖和绑定，默认不开麦。未配置语音不影响任务同步。
- **视觉**：在「机器人 → 看见你」手动开启；详见[本地视觉说明](VISUAL_INTERACTION.md)，默认关闭，锁屏停止。

## 常用操作

| 操作 | 结果 |
| --- | --- |
| 轻点主屏／滑动列表 | 查看任务 |
| 按住待回应卡片或接力条目约 0.9 秒 | 请求 Mac 打开对应对话，不自动回复 |
| 轻摸头 | 表情回应；是否点头由设置决定 |
| 主屏「音乐」 | 音乐详情与播放控制 |
| 番茄钟轻点／退出／结束 | 显控／返回主屏继续计时／取消循环 |
| Control + Option + Space | 控制台运行时进入或退出精简语音模式，须先满足耳机与权限条件 |
| `./weiguang pause` / `resume` | 暂停／恢复同步 |
| `./weiguang diagnostics` | 导出不含任务、便签、音乐或聊天正文的诊断摘要 |

[日常使用](DAILY_USE.md) · [换电脑](MIGRATION.md) · [隐私与局限](docs/PRIVACY.md) · [更新日志](CHANGELOG.md)

## 验证与限制

公开镜像另行运行自动检查与构建，结果见[开发说明](docs/DEVELOPMENT.md)。实机测试不代表其他设备或长期运行保证。任务完成表示一次回复结束，不保证整个项目已完成。

任务读取依赖 Codex 本地数据库／事件格式；音乐依赖 macOS 非公开媒体接口；原厂语音依赖既有设备身份与云服务。这些都不是本项目能保证稳定的外部契约。基础任务同步、番茄钟和便签不需要模型调用；原厂语音不能承诺永久免费。

## 许可证

原创代码采用 [MIT](LICENSE)。第三方驱动和 pyserial 保留各自许可证；语音、音乐、视觉相关依赖见[第三方来源](THIRD_PARTY.md)。原厂云服务、角色和音色不在本项目许可证授权范围内。
