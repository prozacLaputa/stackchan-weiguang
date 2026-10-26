# 微光控制台：Mac 本机安装

当前 App 为 0.49.0 (50)，固件协议为 0.49。本节说明把已有安装迁到「应用程序」。仓库仅发布源码，没有 Developer ID 公证的下载包。

## 日常入口与路径

- 从「应用程序 → 微光控制台」、Spotlight 或 Dock 打开；正式路径为 `/Applications/微光控制台.app`，也支持当前用户的 `Applications` 目录。
- `⌘0` 显示控制台，`⌘W` 收起窗口，`⌘H` 隐藏，`⌘Q` 退出。菜单栏继续提供入口；同步后台与控制台独立。
- 本机数据与组件保存在 `~/Library/Application Support/Weiguang/`；`desktop-components/<安装编号>/` 包含独立 Python 环境，日常使用不需要开发项目。
- 自己的备份位于本机 `private/`，目录 700／文件 600；不进入 `.app`、准备包或公开仓库。旧 App 与路径配置在 `installation-backups/`，安装回执为 `desktop-install.json`。
- 旧数据目录内的 App 路径保留为兼容链接，指向正式应用，不再维护第二份运行副本。

公开源码使用 `io.github.prozaclaputa.weiguang` 标识。历史私有开发版标识不同，不应同时安装运行；迁移应先核对当前安装和回退方案。

## 前提与构建

先完成 README 的同步安装，并按 [语音设置](HEADPHONES_VOICE_SETUP.md) 准备自己的有效原厂备份、校验文件、ffmpeg／libopus 与语音运行配置。**基础任务同步不需要语音，但当前桌面迁移器会验证已有语音环境。** 未配置时继续使用现有同步安装即可，不要提供他人的备份。

依赖仍由本机提供：Python、ffmpeg／libopus，以及音乐功能可选的 media-control。此 App 不是复制到任意电脑即可运行的自包含产品。

```sh
.venv/bin/python macos/build_panel.py
.venv/bin/python macos/build_icon.py
.venv/bin/python macos/install_desktop.py prepare .runtime/desktop-update/package
.venv/bin/python -m pip download --only-binary=:all: \
  --dest .runtime/desktop-update/wheels -r bridge/voice-requirements.txt
# 先正常退出控制台；准备和安装均不刷机器人。
.venv/bin/python macos/install_desktop.py install .runtime/desktop-update/package \
  --wheelhouse .runtime/desktop-update/wheels
```

每次使用新的准备目录。准备阶段仅打包显式组件与图标，验证签名及静音自检；安装阶段离线准备环境并校验自己的身份，再原子切换。切换失败回退旧 App 与配置。默认目标为 `/Applications`；无写权限时可传 `--destination "$HOME/Applications/微光控制台.app"`，并确保该目录存在。

## 后台与固件更新

桌面安装器升级 App 和可选语音／视觉组件，**不自动覆盖已运行的同步后台**。主会话筛选、动作恢复协议等桥接改动，还须暂停同步、备份并更新用户数据目录 `app/` 中相应模块，再恢复；不要只替换 App 就认为后台已升级。

本版涉及 `monitor.py`、`runtime.py`、`task_actions.py`、`control.py`、`diagnostics.py`，其余依赖以 `bridge/service.py` 的 `APP_FILES` 为准。更新前后核对配置、绑定及设备设置，并保留旧文件。通用会话跳转与大字主屏需配套固件 0.49，请先更新 Mac 桥接，再更新机器人。动作恢复兼容 0.48／0.49。固件仅在已核对分区布局后更新应用分区，保留自己的校准和绑定，见 [硬件说明](docs/HARDWARE.md)。

语音仍只走已授权的 AirPods，不修改系统音量、不回退外放。当前公开更新仅含源码与文档，不包含任何人的本机身份、原厂备份或应用二进制。
