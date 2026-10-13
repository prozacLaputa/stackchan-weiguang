"""从可编辑的原生矢量图形生成 macOS 多分辨率图标，无外部依赖。"""
from pathlib import Path
import shutil
import subprocess
root=Path(__file__).resolve().parent
cache=root.parent/'.runtime/icon-build';cache.mkdir(parents=True,exist_ok=True)
iconset=cache/'Weiguang.iconset'
runner=cache/'draw-icon'
subprocess.run(['xcrun','swiftc',str(root/'draw_icon.swift'),'-module-cache-path',str(cache/'swift-cache'),'-o',str(runner),'-framework','AppKit'],check=True)
subprocess.run([str(runner),str(iconset)],check=True)
subprocess.run(['iconutil','-c','icns',str(iconset),'-o',str(root/'Weiguang.icns')],check=True)
shutil.copy2(iconset/'icon_512x512@2x.png',root/'Weiguang.png')
print(root/'Weiguang.icns')
