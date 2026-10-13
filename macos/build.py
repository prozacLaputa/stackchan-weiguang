"""构建带蓝牙用途说明的原生 Mac helper；不安装全局依赖。"""
from pathlib import Path
import subprocess,sys
root=Path(__file__).resolve().parent
output=Path(sys.argv[1]) if len(sys.argv)>1 else root/'WeiguangBluetooth'
output.parent.mkdir(parents=True,exist_ok=True)
cache=root.parent/'.runtime/swift-cache';cache.mkdir(parents=True,exist_ok=True)
parts=[]
for arch in ('arm64','x86_64'):
    part=cache/f'WeiguangBluetooth-{arch}'
    subprocess.run(['xcrun','swiftc',str(root/'WeiguangBluetooth.swift'),'-O','-target',f'{arch}-apple-macosx12.0','-module-cache-path',str(cache),'-o',str(part),'-framework','CoreBluetooth','-Xlinker','-sectcreate','-Xlinker','__TEXT','-Xlinker','__info_plist','-Xlinker',str(root/'Info.plist')],check=True)
    parts.append(str(part))
subprocess.run(['xcrun','lipo','-create',*parts,'-output',str(output)],check=True)
subprocess.run(['codesign','--force','--sign','-','--identifier','io.github.prozaclaputa.weiguang.bluetooth',str(output)],check=True)
print(output)
