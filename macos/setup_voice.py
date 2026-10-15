"""为本机控制台启用已验证的原厂语音路径；不搬运备份／凭据，不改机器人或桥接服务。"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent.parent


def main():
    target=Path.home()/'Library/Application Support/Weiguang'
    binary=target/'微光控制台.app/Contents/MacOS/WeiguangPanel'
    config=target/'voice-runtime.json'
    python=ROOT/'.venv/bin/python'
    worker=ROOT/'bridge/factory_voice_client.py'
    ffmpeg=Path(shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg')
    opus=next((p for p in (Path('/opt/homebrew/lib/libopus.dylib'),Path('/usr/local/lib/libopus.dylib')) if p.is_file()),None)
    if not binary.is_file() or not (target/'config.json').is_file():raise RuntimeError('existing_installation_required')
    if not opus or not all(p.is_file() for p in (python,worker,ffmpeg,ROOT/'macos/WeiguangPanel',ROOT/'backups/factory.bin')):raise RuntimeError('voice_dependencies_missing')
    sys.path.insert(0,str(ROOT/'checks'))
    from factory_voice_identity import read_identity,summary
    if not summary(read_identity())['bound_device_matches_mqtt_client']:raise RuntimeError('device_identity_mismatch')
    # 只备份将覆盖的控制台与本机路径配置，不复制连接秘密。
    before=ROOT/'.runtime/voice'/('install-before-'+str(time.time_ns()))
    before.mkdir(parents=True,mode=0o700)
    bundle=binary.parents[2]
    shutil.copytree(bundle,before/'微光控制台.app')
    if config.exists():shutil.copy2(config,before/config.name)
    staged=target/f'.weiguang-voice-new-{time.time_ns()}.app'
    shutil.copytree(bundle,staged)
    staged_binary=staged/'Contents/MacOS/WeiguangPanel'
    shutil.copy2(ROOT/'macos/WeiguangPanel',staged_binary);staged_binary.chmod(0o755)
    shutil.copy2(ROOT/'macos/PanelInfo.plist',staged/'Contents/Info.plist')
    subprocess.run(['codesign','--force','--sign','-','--identifier','io.github.prozaclaputa.weiguang.panel',str(staged)],check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['codesign','--verify','--strict',str(staged)],check=True)
    previous=target/f'.weiguang-voice-previous-{time.time_ns()}.app'
    os.replace(bundle,previous)
    try:os.replace(staged,bundle)
    except BaseException:
        os.replace(previous,bundle);raise
    shutil.rmtree(previous) # 完整旧应用已保存在本项目的 before 目录。

    data={'python':str(python),'worker':str(worker),'ffmpeg':str(ffmpeg),'libopus':str(opus)}
    stage=config.with_suffix('.new')
    descriptor=os.open(stage,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(descriptor,'w') as handle:json.dump(data,handle,ensure_ascii=False,indent=2)
    os.replace(stage,config);config.chmod(0o600)
    print(json.dumps({'ok':True,'voice_preferences_preserved':True,'credentials_copied':False,'bridge_restarted':False,
                      'panel_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'ok':False,'error_type':type(error).__name__}));sys.exit(1)
