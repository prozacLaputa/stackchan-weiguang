# 换电脑与恢复

保存源码、自行构建的 Mac 二进制和你自己的原厂备份。公开源码不包含任何人的工厂固件、密钥或会话文件。

## 新 Mac

按 README 构建，USB 连接设备后运行 `./weiguang install`，再运行 `./weiguang bind-bluetooth` 重新绑定并授予系统蓝牙权限。不要拷贝旧机器的 LaunchAgent 或蓝牙密钥。设备上的外观／动作设置、已保存专注统计和便签仍由设备保存。

## 离线迁移包

本机完成构建后可运行 `./weiguang export ~/Desktop/weiguang-migration.zip`，包含本地安装所需文件，不包括绑定密钥和聊天。解压后执行包内 `./weiguang install`。下载过的离线 pyserial wheel 已随源码提供，安装时校验 SHA-256。

可选 `--include-factory-backup` 仅用于你的私人归档；它读取项目下的 `backups/factory.bin` 与 `backups/factory.sha256`，验证完整 16 MB 镜像。**包含原厂备份的包不可作为 GitHub Release 附件。** 若设备不是 16 MB，不使用这项打包流程。

原厂恢复依赖你自己设备的完整备份及正确分区；本项目没有实际执行并验证完整原厂恢复。不要把“备份校验通过”理解成“恢复已验收”。
