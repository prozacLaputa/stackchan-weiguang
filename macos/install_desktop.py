"""微光本机桌面安装：无凭据应用包 + 当前用户的私有运行目录。

prepare 只组装程序；install 要求控制台已退出，离线准备依赖后原子切换。
不刷机器人、不启动录音、不调用云服务，不改后台同步与用户偏好。
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time
import venv

ROOT = Path(__file__).resolve().parent.parent
NAME = '微光控制台.app'
IDENTIFIER = 'io.github.prozaclaputa.weiguang.panel'
RUNTIME_FILES = ('bridge/factory_voice_client.py', 'bridge/voice_commands.py',
                 'bridge/vision_camera.py', 'bridge/runtime.py', 'bridge/presence.py',
                 'bridge/control.py', 'bridge/ble_link.py', 'bridge/monitor.py',
                 'bridge/expression.py', 'bridge/waiting_reason.py', 'bridge/completion_summary.py',
                 'bridge/task_progress.py', 'bridge/diagnostics.py', 'bridge/desk_extras.py',
                 'bridge/recovery.py', 'bridge/task_actions.py',
                 'checks/factory_voice_identity.py', 'checks/factory_voice_probe.py')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_name(path.name+'.new')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
    temp.chmod(0o600);os.replace(temp,path)


def run(args, **options):
    return subprocess.run([str(x) for x in args],check=True,timeout=120,**options)


def verify_bundle(bundle):
    info=plistlib.loads((bundle/'Contents/Info.plist').read_bytes())
    if info.get('CFBundleIdentifier')!=IDENTIFIER or info.get('CFBundleExecutable')!='WeiguangPanel':
        raise ValueError('unexpected_app_identity')
    run(['codesign','--verify','--strict',bundle],capture_output=True)
    return info


def prepare(destination):
    destination=Path(destination).resolve()
    destination.mkdir(parents=True,exist_ok=False)
    contents=destination/NAME/'Contents'
    (contents/'MacOS').mkdir(parents=True);(contents/'Resources').mkdir()
    for source,target in [('WeiguangPanel','MacOS/WeiguangPanel'),('PanelInfo.plist','Info.plist'),('Weiguang.icns','Resources/Weiguang.icns')]:
        shutil.copy2(ROOT/'macos'/source,contents/target)
    (contents/'MacOS/WeiguangPanel').chmod(0o755)
    for relative in RUNTIME_FILES:
        target=destination/'components'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target)
    shutil.copy2(ROOT/'bridge/voice-requirements.txt',destination/'voice-requirements.txt')
    run(['codesign','--force','--sign','-','--identifier',IDENTIFIER,destination/NAME])
    info=verify_bundle(destination/NAME)
    for option in ('--self-test','--voice-self-test'):
        run([contents/'MacOS/WeiguangPanel',option],capture_output=True)
    manifest={str(p.relative_to(destination)):digest(p) for p in destination.rglob('*') if p.is_file()}
    write_json(destination/'manifest.json',manifest)
    print(json.dumps({'prepared':str(destination),'version':info['CFBundleShortVersionString'],'files':len(manifest),'contains_credentials':False},ensure_ascii=False))


def verify_package(package):
    manifest=json.loads((package/'manifest.json').read_text())
    actual={str(p.relative_to(package)) for p in package.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if actual!=set(manifest):raise ValueError('package_files_changed')
    for relative,expected in manifest.items():
        p=package/relative
        if p.is_symlink() or not p.resolve().is_relative_to(package.resolve()) or digest(p)!=expected:
            raise ValueError('package_checksum_mismatch')
    return verify_bundle(package/NAME)


def validate_destination(destination, home):
    if destination not in (Path('/Applications')/NAME,home/'Applications'/NAME):
        raise ValueError('unsupported_application_destination')
    if destination.is_symlink():raise ValueError('application_destination_is_symlink')


def install(package, wheelhouse, destination):
    package=Path(package).resolve();wheelhouse=Path(wheelhouse).resolve();destination=Path(destination).absolute()
    home=Path.home();support=home/'Library/Application Support/Weiguang';legacy=support/NAME
    validate_destination(destination,home)
    info=verify_package(package)
    config=json.loads((support/'config.json').read_text())
    if config.get('app_id')!='io.github.prozaclaputa.weiguang':raise ValueError('existing_installation_required')
    verify_bundle(legacy)
    if destination.exists():verify_bundle(destination)
    # 不终止未知进程；调用方先正常退出控制台，后台同步保持运行。
    processes=subprocess.run(['/usr/bin/pgrep','-f','/WeiguangPanel$'],capture_output=True,text=True)
    if processes.returncode==0:raise RuntimeError('quit_panel_before_installing')
    if processes.returncode!=1:raise RuntimeError('cannot_check_panel_processes')
    before_config=(support/'voice-runtime.json').read_bytes()
    previous=json.loads(before_config)
    for key in ('ffmpeg','libopus'):
        if not Path(previous[key]).is_file():raise ValueError('audio_dependency_missing')
    stamp=str(time.time_ns())
    release=support/'desktop-components'/stamp
    release.mkdir(parents=True,mode=0o700)
    for folder in ('bridge','checks'):shutil.copytree(package/'components'/folder,release/folder)
    # 每个版本独立环境，准备失败不影响当前安装；不复制开发 venv 的绝对路径。
    venv.EnvBuilder(with_pip=True,symlinks=False).create(release/'.venv')
    python=release/'.venv/bin/python'
    run([python,'-m','pip','install','--no-index','--find-links',wheelhouse,
         '--disable-pip-version-check','--no-cache-dir','-r',package/'voice-requirements.txt'],capture_output=True)
    source_backup=ROOT/'backups/factory.bin'
    source_digest=ROOT/'backups/factory.sha256'
    private=support/'private';private.mkdir(mode=0o700,exist_ok=True);private.chmod(0o700)
    backup=private/'factory.bin';checksum=private/'factory.sha256'
    if backup.exists()!=checksum.exists():raise ValueError('incomplete_private_backup')
    if not backup.exists():
        expected=source_digest.read_text().split()[0]
        if source_backup.stat().st_size!=16777216 or digest(source_backup)!=expected:raise ValueError('factory_backup_mismatch')
        # 私密身份只进入当前用户数据目录，不进入 .app、prepared package 或公开仓库。
        fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(source_backup.read_bytes())
        fd=os.open(checksum,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(expected+'  factory.bin\n')
    (release/'backups').symlink_to(private,target_is_directory=True)
    # 从新安装位置离线验证依赖、原厂备份及机器人身份，不发云请求。
    probe="""import ctypes,sys
sys.dont_write_bytecode=True
sys.path[:0]=[sys.argv[1]+'/bridge',sys.argv[1]+'/checks']
import serial,certifi,cryptography,factory_voice_client,vision_camera
from factory_voice_identity import read_identity,summary
assert summary(read_identity())['bound_device_matches_mqtt_client']
ctypes.CDLL(sys.argv[2])
print('installed components and identity verified offline')
"""
    run([python,'-I','-c',probe,release,previous['libopus']],cwd='/private/tmp',capture_output=True)
    new_config={'python':str(python),'worker':str(release/'bridge/factory_voice_client.py'),
                'ffmpeg':previous['ffmpeg'],'libopus':previous['libopus']}
    backup_dir=support/'installation-backups'/stamp;backup_dir.mkdir(parents=True,mode=0o700)
    for name in ('voice-runtime.json','desktop-install.json'):
        if (support/name).exists():shutil.copy2(support/name,backup_dir/name)
    destination.parent.mkdir(parents=True,exist_ok=True)
    staged=destination.with_name('.weiguang-install-'+stamp+'.app')
    shutil.copytree(package/NAME,staged);verify_bundle(staged)
    old_destination=backup_dir/'previous-app.app'
    old_legacy=backup_dir/'legacy-app.app'
    moved_destination=False;moved_legacy=False;installed_app=False
    try:
        if destination.exists():os.replace(destination,old_destination);moved_destination=True
        os.replace(staged,destination);installed_app=True
        os.replace(legacy,old_legacy);moved_legacy=True
        legacy.symlink_to(destination,target_is_directory=True)
        write_json(support/'voice-runtime.json',new_config)
        verify_bundle(destination)
        for option in ('--self-test','--voice-self-test'):
            run([destination/'Contents/MacOS/WeiguangPanel',option],capture_output=True)
        receipt={'bundle_path':str(destination),'version':info['CFBundleShortVersionString'],
                 'build':info['CFBundleVersion'],'components':str(release),'backup_dir':str(backup_dir),
                 'bundle_id':IDENTIFIER,'installed_at':time.time(),'credentials_in_app':False,
                 'bridge_restarted':False,'factory_backup_sha256':digest(backup)}
        write_json(support/'desktop-install.json',receipt)
        write_json(backup_dir/'receipt.json',receipt)
    except BaseException:
        if moved_legacy:
            if legacy.is_symlink():legacy.unlink()
            os.replace(old_legacy,legacy)
        if installed_app:os.replace(destination,backup_dir/'failed-app.app')
        if moved_destination:os.replace(old_destination,destination)
        (support/'voice-runtime.json').write_bytes(before_config);(support/'voice-runtime.json').chmod(0o600)
        old_marker=backup_dir/'desktop-install.json'
        if old_marker.exists():shutil.copy2(old_marker,support/'desktop-install.json')
        else:(support/'desktop-install.json').unlink(missing_ok=True)
        raise
    print(json.dumps({'installed':str(destination),'version':info['CFBundleShortVersionString'],
                      'rollback':str(backup_dir),'developer_folder_required':False,
                      'system_dependencies':['Python 3.13','ffmpeg','libopus','media-control']},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('prepare').add_argument('destination')
    setup=commands.add_parser('install');setup.add_argument('package');setup.add_argument('--wheelhouse',required=True)
    setup.add_argument('--destination',default='/Applications/'+NAME)
    args=parser.parse_args()
    if args.command=='prepare':prepare(args.destination)
    else:install(args.package,args.wheelhouse,args.destination)
