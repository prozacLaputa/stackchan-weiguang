# 开发与验证

## 组成

- `src/`：设备 UI、手势、任务与连接状态、表情、限幅动作、计时和便签。
- `bridge/`：只读 Codex 状态、USB／BLE 调度、本地控制 socket、登录服务和诊断。
- `macos/`：SwiftUI 控制台、CoreBluetooth helper、图标源文件和本地构建脚本。
- `lib/`：按范围保留并带许可证的硬件驱动。
- `tests/`、`bridge/test_*.py`：使用假设备／隔离文件的宿主测试。

固件依赖固定为 espressif32 6.12.0、M5GFX 0.2.31、M5Unified 0.2.25；使用标准注册表下载，不依赖开发者本地 vendor 目录。Python 运行依赖只有 pyserial 3.5，离线 wheel 在安装前验证哈希。

## 测试

完成 README 的 Python 依赖安装后：

```sh
.venv/bin/pio run
.venv/bin/python checks/run_tests.py
# 在本机完成原生构建后
macos/WeiguangPanel --self-test
# 只生成示例数据渲染预览
python3 checks/render_preview.py
```

触摸流水线检查直接引用固定版本 M5Unified 的实际实现，因此先执行固件构建下载依赖。测试运行需要本机临时 Unix socket 和伪终端权限，不连接真实机器人、不读取真实聊天。C++ 检查启用 AddressSanitizer / UndefinedBehaviorSanitizer。

## 候选状态

开发版本已通过 122 项 Python 测试、27 组 C++ 检查、固件编译和 Swift 双架构开发构建。公开副本已单独通过 122 项 Python 测试、27 组 C++ ASan/UBSan 检查，以及 Swift 两个组件的 arm64／x86_64 类型检查。触摸测试使用从官方注册表新获取的 M5Unified 0.2.25。没有构建或签名发行 App。

公开副本已使用官方注册表平台／编译器、官方固定版本 SDK、M5GFX 0.2.31 和 M5Unified 0.2.25 完成完整固件构建。SDK 主镜像下载慢，改用注册表返回的备用镜像并校验官方 SHA-256 后成功。构建不依赖私人 vendor 缓存。

实机运行的是同一 v0.46 固件源码的开发环境构建，公开环境构建另作编译验证。设备显示、Mac 便签收发与重启保留已检查；手指长按手感、Mac 自然登录、全天稳定性和原厂完整恢复不列为已验收。没有可下载的签名、公证 Mac 发行包。


2026-10-13 长按交互修正：主屏与番茄钟待回应区改为持续按住约 0.9 秒即发送请求。源固件／公开固件重新编译成功，27 组 C++ 回归通过，公开副本另行运行两组受影响检查。开发设备已刷入，使用者确认无需松手即可打开；便签长按收起的人工手感仍待体验。


同日便签外观更新为暖黄色纸张、深棕字、纸纹和折角。仅修改绘制，源／公开副本重新编译成功，开发设备刷入与真实帧缓冲视觉检查通过；既有交互测试结论沿用上一轮，不声称这次重跑所有测试。
