"""编译原生控制台；安装与迁移只需要产物，不需要 Swift 工具链。"""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parent
cache=root.parent/'.runtime/swift-cache';cache.mkdir(parents=True,exist_ok=True)
parts=[]
for arch in ('arm64','x86_64'):
 part=cache/f'WeiguangPanel-{arch}'
 subprocess.run(['xcrun','swiftc',*[str(root/name) for name in ('WeiguangPanel.swift','AirPodsAudio.swift','VoiceCompanion.swift','VoiceViews.swift','VoiceGreeting.swift','VoiceConversation.swift','VoiceFace.swift','VoiceMicrophone.swift','VoiceMode.swift','VoiceTaskNotice.swift','VoiceCommands.swift','VoiceHotkey.swift','LocalVision.swift','DeskExtras.swift')],'-parse-as-library','-O','-target',f'{arch}-apple-macosx12.0','-module-cache-path',str(cache),'-o',str(part),'-framework','SwiftUI','-framework','AppKit','-framework','CoreAudio','-framework','AudioToolbox','-framework','AVFoundation','-framework','Carbon','-framework','Vision'],check=True)
 parts.append(str(part))
subprocess.run(['xcrun','lipo','-create',*parts,'-output',str(root/'WeiguangPanel')],check=True)
subprocess.run(['codesign','--force','--sign','-','--identifier','io.github.prozaclaputa.weiguang.panel',str(root/'WeiguangPanel')],check=True)
print(root/'WeiguangPanel')
