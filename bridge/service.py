"""可迁移的微光用户级 LaunchAgent 管理入口，不需要 sudo。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import secrets
import shutil
import subprocess
import sys
import time
import venv
import zipfile
from runtime import atomic_json, select_port

LABEL = 'io.github.prozaclaputa.weiguang'
WHEEL_HASH = 'c4451db6ba391ca6ca299fb3ec7bae67a5c55dde170964c7a14ceefec02f2cf0'
APP_FILES = ('desk_extras.py', 'monitor.py', 'expression.py', 'waiting_reason.py', 'completion_summary.py', 'task_progress.py', 'task_actions.py', 'diagnostics.py', 'runtime.py', 'presence.py', 'service.py', 'requirements.txt', 'ble_link.py', 'control.py', 'recovery.py')
PROJECT = Path(__file__).resolve().parent.parent


class Locations:
    def __init__(self, home=None):
        self.home = Path(home or Path.home())
        self.root = self.home/'Library/Application Support/Weiguang'
        self.plist = self.home/'Library/LaunchAgents'/f'{LABEL}.plist'
        self.config = self.root/'config.json'
        self.runtime = self.root/'runtime'
        self.python = self.root/'.venv/bin/python'
        self.target = f'gui/{os.getuid()}/{LABEL}'
        self.domain = f'gui/{os.getuid()}'


def launch(*args, check=True):
    result = subprocess.run(['/bin/launchctl', *args], capture_output=True, text=True, timeout=10)
    if check and result.returncode:
        raise RuntimeError(f'launchctl {args[0]} 失败：{result.stderr.strip()}')
    return result


def owned(loc):
    if not loc.config.exists():
        raise RuntimeError('尚未安装，请先运行 ./weiguang install')
    config = json.loads(loc.config.read_text())
    if config.get('app_id') != LABEL:
        raise RuntimeError('目录中不是本工具创建的配置，已停止操作。')
    return config


def make_plist(loc, config):
    args = [str(loc.python), '-u', str(loc.root/'app/monitor.py'),
            '--runtime-dir', str(loc.runtime), '--port', 'auto',
            '--serial-number', config['serial_number'], '--codex-home', config['codex_home'],
            '--transport', config.get('transport','usb')]
    if config.get('ble_device'):
        args += ['--ble-device',config['ble_device'],'--ble-key-file',str(loc.root/'ble.key'),
                 '--ble-helper',str(loc.root/'微光蓝牙.app/Contents/MacOS/WeiguangBluetooth')]
    args += ['--thread','']
    return {
        'Label': LABEL,
        'ProgramArguments': args,
        'WorkingDirectory': str(loc.root),
        'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 10,
        'ProcessType': 'Background', 'ExitTimeOut': 5, 'Umask': 0o077,
        'StandardOutPath': '/dev/null',
        'StandardErrorPath': str(loc.runtime/'startup-error.log'),
        'EnvironmentVariables': {'PYTHONUNBUFFERED': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1'},
    }


def installed(loc):
    result = launch('print', loc.target, check=False)
    return result.returncode == 0, result.stdout


def stop_loaded(loc):
    loaded, _ = installed(loc)
    if loaded:
        launch('bootout', loc.target)
        deadline = time.monotonic() + 8
        while installed(loc)[0] and time.monotonic() < deadline:
            time.sleep(.1)
        if installed(loc)[0]:
            raise RuntimeError('服务尚未退出，暂不启动另一个实例。')


def save_plist(loc, config):
    loc.plist.parent.mkdir(parents=True, exist_ok=True)
    temp = loc.plist.with_suffix('.tmp')
    with temp.open('wb') as stream:
        plistlib.dump(make_plist(loc, config), stream)
    temp.chmod(0o600)
    temp.replace(loc.plist)


def bind_device(loc, requested):
    if requested:
        return requested
    if loc.config.exists():
        return owned(loc)['serial_number']
    try:
        from serial.tools import list_ports
    except ImportError:
        # 安装脚本本身只用标准库；设备发现由新建的隔离环境执行。
        result = subprocess.run([str(loc.python), '-c',
            'import json; from serial.tools import list_ports; '
            'print(json.dumps([dict(device=p.device,vid=p.vid,pid=p.pid,serial_number=p.serial_number) for p in list_ports.comports()]))'],
            check=True, capture_output=True, text=True)
        from types import SimpleNamespace
        ports = [SimpleNamespace(**row) for row in json.loads(result.stdout)]
    else:
        ports = list(list_ports.comports())
    device = select_port(ports)
    match = next((p for p in ports if p.device == device), None)
    if not match or not match.serial_number:
        raise RuntimeError('请用数据线连接机器人后重新安装；多个设备时传入 --serial-number。')
    return match.serial_number


def check_usb_free(loc, serial_number):
    # 只读检查，不终止无法验证归属的旧进程。
    result = subprocess.run([str(loc.python), '-c',
        'import json; from serial.tools import list_ports; '
        'print(json.dumps([p.device for p in list_ports.comports() if p.serial_number == '+repr(serial_number)+']))'],
        capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('运行环境无法读取 USB 设备，请重新运行 install 修复。')
    for device in json.loads(result.stdout):
        result = subprocess.run(['/usr/sbin/lsof', '-t', device], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            raise RuntimeError('机器人串口仍被其他进程占用，请先停止旧同步程序，再运行 resume。')


def resume(loc):
    config = owned(loc)
    if not loc.plist.exists():
        save_plist(loc, config)
    loaded, _ = installed(loc)
    if not loaded and config.get('transport','usb')!='ble':
        check_usb_free(loc, config['serial_number'])
    launch('enable', loc.target)
    config['paused'] = False
    atomic_json(loc.config, config)
    if not loaded:
        launch('bootstrap', loc.domain, str(loc.plist))
    else:
        launch('kickstart', loc.target)
    print('已开启微光同步；以后登录 Mac 会自动运行。')


def pause(loc):
    config = owned(loc)
    launch('disable', loc.target)
    stop_loaded(loc)
    config['paused'] = True
    atomic_json(loc.config, config)
    print('已暂停；重启 Mac 后也保持暂停，点击“恢复同步”即可重新开启。')


def install(loc, args):
    if sys.platform != 'darwin':
        raise RuntimeError('此安装入口仅支持 macOS。')
    if sys.version_info < (3, 9):
        raise RuntimeError('需要 Python 3.9 或更新版本。')
    previous = owned(loc) if loc.config.exists() else {}
    if loc.root.exists() and not previous and any(loc.root.iterdir()):
        # 允许上次因未接设备而留下的本工具 venv，仍要求标记。
        if not (loc.root/'.weiguang-installing').exists():
            raise RuntimeError('目标目录已有未知文件，未覆盖。')
    if loc.plist.exists():
        with loc.plist.open('rb') as stream:
            existing = plistlib.load(stream)
        if existing.get('Label') != LABEL or existing.get('ProgramArguments', [None])[0] != str(loc.python):
            raise RuntimeError('同名 LaunchAgent 不属于这个安装目录，未覆盖。')
    loc.root.mkdir(parents=True, exist_ok=True, mode=0o700)
    (loc.root/'.weiguang-installing').touch(mode=0o600)
    loc.runtime.mkdir(exist_ok=True, mode=0o700)
    wheel = PROJECT/'bridge/wheels/pyserial-3.5-py2.py3-none-any.whl'
    if not wheel.exists() or hashlib.sha256(wheel.read_bytes()).hexdigest() != WHEEL_HASH:
        raise RuntimeError('离线 pyserial 安装包缺失或校验失败，请使用完整迁移包。')
    # 先准备依赖，失败时不打断已运行的版本。
    if not loc.python.exists():
        venv.EnvBuilder(with_pip=True).create(loc.root/'.venv')
    subprocess.run([str(loc.python), '-m', 'pip', 'install', '--disable-pip-version-check',
                    '--no-index', '--no-deps', '--no-cache-dir', str(wheel)], check=True)
    serial_number = bind_device(loc, args.serial_number)
    config = dict(app_id=LABEL, version=1, serial_number=serial_number,
                  codex_home=str(Path(args.codex_home or previous.get('codex_home') or
                                      os.environ.get('CODEX_HOME', Path.home()/'.codex')).expanduser().resolve()),
                  paused=previous.get('paused', False))
    native=PROJECT/'macos/WeiguangBluetooth'
    if not native.is_file():
        raise RuntimeError('缺少原生蓝牙助手，请使用完整迁移包或运行 python3 macos/build.py。')
    panel=PROJECT/'macos/WeiguangPanel'
    if not panel.is_file() or not (PROJECT/'macos/PanelInfo.plist').is_file() or not (PROJECT/'macos/Weiguang.icns').is_file():
        raise RuntimeError('缺少微光控制台，请使用完整迁移包或运行 python3 macos/build_panel.py。')
    config['version']=2
    config['transport']=previous.get('transport','usb')
    if previous.get('ble_device'):config['ble_device']=previous['ble_device']
    stop_loaded(loc)
    bundle=loc.root/'微光蓝牙.app/Contents'
    (bundle/'MacOS').mkdir(parents=True,exist_ok=True)
    shutil.copy2(native,bundle/'MacOS/WeiguangBluetooth')
    (bundle/'MacOS/WeiguangBluetooth').chmod(0o755)
    shutil.copy2(PROJECT/'macos/Info.plist',bundle/'Info.plist')
    # 正式安装保留旧路径兼容链接；更新实际应用，避免重新生成第二份控制台。
    panel_path=(loc.root/'微光控制台.app').resolve()
    if (loc.root/'微光控制台.app').is_symlink() and panel_path not in (
            Path('/Applications/微光控制台.app'),loc.home/'Applications/微光控制台.app'):
        raise RuntimeError('控制台链接不指向受支持的应用目录，未覆盖。')
    panel_bundle=panel_path/'Contents'
    (panel_bundle/'MacOS').mkdir(parents=True,exist_ok=True)
    shutil.copy2(panel,panel_bundle/'MacOS/WeiguangPanel')
    (panel_bundle/'MacOS/WeiguangPanel').chmod(0o755)
    shutil.copy2(PROJECT/'macos/PanelInfo.plist',panel_bundle/'Info.plist')
    (panel_bundle/'Resources').mkdir(exist_ok=True)
    shutil.copy2(PROJECT/'macos/Weiguang.icns',panel_bundle/'Resources/Weiguang.icns')
    subprocess.run(['codesign','--force','--sign','-','--identifier',LABEL+'.panel',str(panel_path)],check=True)
    app = loc.root/'app'
    app.mkdir(exist_ok=True)
    for filename in APP_FILES:
        shutil.copy2(PROJECT/'bridge'/filename, app/filename)
    shutil.copy2(PROJECT/'bridge/wheels/pyserial-3.5-LICENSE.txt', app/'pyserial-LICENSE.txt')
    atomic_json(loc.config, config)
    save_plist(loc, config)
    (loc.root/'.weiguang-installing').unlink(missing_ok=True)
    if config['paused']:
        print('安装已更新，保留原先的暂停状态。运行 resume 可恢复。')
    else:
        resume(loc)
    print(f'运行目录：{loc.root}')


def status(loc, as_json=False, emit=True):
    if not loc.config.exists() or not loc.plist.exists():
        result = {'installed': False}
    else:
        config = owned(loc)
        loaded, description = installed(loc)
        match = re.search(r'^\s*pid = (\d+)', description, re.M)
        pid = int(match[1]) if match else None
        try:
            bridge = json.loads((loc.runtime/'status.json').read_text())
        except (OSError, ValueError):
            bridge = {}
        fresh = pid is not None and bridge.get('pid') == pid and 0 <= time.time()-bridge.get('updated_at', 0) < 15
        result = dict(installed=True, paused=config.get('paused', False), loaded=loaded, pid=pid,
                      fresh=fresh, bridge=bridge if fresh else None)
    if not emit:return result
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif not result['installed']:
        print('微光尚未安装。先连接机器人，再运行 ./weiguang install。')
    else:
        print('登录自启：' + ('暂停' if result['paused'] else '开启'))
        print('同步进程：' + ('运行中' if result['pid'] else '未运行'))
        bridge = result['bridge'] or {}
        names = {'connected': '已连接，机器人已确认收到', 'waiting_usb': '等待 USB 连接',
                 'waiting_ble': '等待蓝牙连接', 'waiting_ack': '链路已打开，等待机器人确认', 'stopped': '已停止'}
        print('机器人：' + names.get(bridge.get('connection'), '暂无新状态'))
        if bridge:
            print('通道：' + {'ble':'蓝牙','usb':'USB'}.get(bridge.get('transport'),'等待连接'))
            if bridge.get('error'):print('连接提示：' + bridge['error'])
            print('Codex 数据：' + ('可读取' if bridge['data_source']=='ok' else '暂不可读取，等待恢复'))
            print(f"任务 {bridge['tasks']} · 运行 {bridge['running']} · 待回应 {bridge['needs_input']}")
        print(f'日志：{loc.runtime / "bridge.log"}')
    return result


def bind_bluetooth(loc):
    config=owned(loc)
    was_paused=config.get('paused',False)
    if not was_paused:pause(loc)
    try:
        key_path=loc.root/'ble.key'
        key=key_path.read_text().strip() if key_path.exists() else secrets.token_hex(32)
        if not re.fullmatch('[0-9a-f]{64}',key):raise RuntimeError('本地绑定密钥格式不正确，未改动机器人。')
        # 密钥通过 stdin 交给可信的本机串口进程，不写入命令行参数或日志。
        program = """
import json,sys,time,serial
from serial.tools import list_ports
config=json.load(sys.stdin)
ports=[p.device for p in list_ports.comports() if p.device.startswith('/dev/cu.') and p.serial_number==config['serial_number']]
if len(ports)!=1:raise SystemExit('请用 USB 数据线连接已绑定的机器人后重试')
s=serial.Serial();s.port=ports[0];s.baudrate=115200;s.timeout=.2;s.write_timeout=3;s.dtr=False;s.rts=False;s.exclusive=True;s.open()
try:
    time.sleep(3);s.reset_input_buffer();s.write(('BIND_BLE\\t'+config['key']+'\\n').encode())
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        line=s.readline().decode(errors='replace').strip()
        if line.startswith('BIND\\tok\\t'):
            print(json.dumps({'device':line.split('\\t')[2]}));break
    else:raise SystemExit('机器人未确认蓝牙绑定；请确认已刷入 v0.21 固件')
finally:s.close()
"""
        result=subprocess.run([str(loc.python),'-c',program],input=json.dumps({'serial_number':config['serial_number'],'key':key}),capture_output=True,text=True,timeout=15)
        if result.returncode:raise RuntimeError(result.stderr.strip() or 'USB 绑定失败')
        device=json.loads(result.stdout)['device']
        if not re.fullmatch('[0-9a-f]{12}',device):raise RuntimeError('设备身份回复无效')
        temp=key_path.with_suffix('.tmp')
        with temp.open('w') as stream:
            os.chmod(temp,0o600);stream.write(key+'\n')
        temp.replace(key_path)
        config=owned(loc);config['ble_device']=device;config['transport']='ble'
        atomic_json(loc.config,config);save_plist(loc,config)
        print('蓝牙设备已绑定；日常数据将使用蓝牙，USB 可单独用于供电或调试。')
    finally:
        if not was_paused:resume(loc)


def change_transport(loc,transport):
    config=owned(loc)
    if transport!='usb' and not config.get('ble_device'):raise RuntimeError('请先用 USB 连接并运行 bind-bluetooth')
    stop_loaded(loc);config['transport']=transport;atomic_json(loc.config,config);save_plist(loc,config)
    if not config.get('paused'):resume(loc)


def uninstall(loc):
    owned(loc)
    launch('disable', loc.target)
    stop_loaded(loc)
    loc.plist.unlink(missing_ok=True)
    # 留住配置和日志；不删除固件、备份或源项目。
    config = owned(loc)
    config['paused'] = True
    atomic_json(loc.config, config)
    print('已移除登录自启；本地配置、项目与机器人固件保留。')


def export_package(destination, include_backup=False):
    destination = Path(destination).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError('导出目标已存在，请换一个文件名。')
    paths = [PROJECT/'weiguang', PROJECT/'DAILY_USE.md', PROJECT/'MIGRATION.md', PROJECT/'VISUAL_INTERACTION.md', PROJECT/'LOCAL_APP_INSTALL.md']
    paths += [PROJECT/'bridge'/name for name in APP_FILES]
    paths += list((PROJECT/'controls').glob('*.command'))
    # 仅源码与说明；语音身份、获准耳机UID和本机路径均不进入迁移包。
    paths += [PROJECT/'macos/setup_voice.py',PROJECT/'macos/install_desktop.py',PROJECT/'bridge/voice-requirements.txt',PROJECT/'bridge/factory_voice_client.py',PROJECT/'bridge/voice_commands.py',PROJECT/'bridge/vision_camera.py',PROJECT/'HEADPHONES_VOICE_SETUP.md']
    paths += [PROJECT/'checks'/name for name in ('factory_voice_identity.py','factory_voice_probe.py')]
    paths += [PROJECT/'macos'/name for name in ('WeiguangBluetooth','Info.plist','WeiguangBluetooth.swift','build.py','WeiguangPanel','PanelInfo.plist','WeiguangPanel.swift','AirPodsAudio.swift','VoiceCompanion.swift','VoiceViews.swift','VoiceGreeting.swift','VoiceConversation.swift','VoiceFace.swift','VoiceMicrophone.swift','VoiceMode.swift','VoiceTaskNotice.swift','VoiceCommands.swift','VoiceHotkey.swift','LocalVision.swift','DeskExtras.swift','build_panel.py','Weiguang.icns','Weiguang.png','draw_icon.swift','build_icon.py')]
    # 新电脑通过 USB 重新绑定；不导出当前机器的 ble.key 或蓝牙权限。
    paths += [PROJECT/'bridge/wheels/pyserial-3.5-py2.py3-none-any.whl',
              PROJECT/'bridge/wheels/pyserial-3.5-LICENSE.txt']
    if include_backup:
        image = PROJECT/'backups/factory.bin'
        digest = PROJECT/'backups/factory.sha256'
        expected = digest.read_text().split()[0]
        if image.stat().st_size != 16_777_216 or hashlib.sha256(image.read_bytes()).hexdigest() != expected:
            raise RuntimeError('原厂备份校验失败，未打包。')
        paths += [image, digest]
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as archive:
        manifest = {}
        for path in paths:
            name = 'weiguang-migration/' + path.relative_to(PROJECT).as_posix()
            archive.write(path, name)
            manifest[str(path.relative_to(PROJECT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        archive.writestr('weiguang-migration/SHA256SUMS.json', json.dumps(manifest, indent=2)+'\n')
    destination.chmod(0o600)
    print(f'迁移包已生成：{destination}')
    print('原厂备份：' + ('已包含（私人文件，请勿公开上传）' if include_backup else '未包含，请另外保管 backups 目录'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='action', required=True)
    setup = sub.add_parser('install', help='安装或更新登录自启')
    setup.add_argument('--serial-number')
    setup.add_argument('--codex-home')
    sub.add_parser('bind-bluetooth', help='通过 USB 绑定蓝牙设备并启用无线同步')
    mode=sub.add_parser('transport', help='选择日常同步通道')
    mode.add_argument('mode', choices=('usb','ble','auto'))
    sub.add_parser('pause', help='暂停同步，跨重启保持')
    sub.add_parser('resume', help='恢复同步和登录自启')
    sub.add_parser('restart', help='重启已启用的同步进程')
    recovery = sub.add_parser('recover', help='重建连接并等待机器人新回执')
    recovery.add_argument('--resume', action='store_true', help='显式恢复已暂停的同步')
    recovery.add_argument('--json', action='store_true')
    state = sub.add_parser('status', help='查看状态')
    state.add_argument('--json', action='store_true')
    sub.add_parser('diagnostics', help='导出不含聊天和密钥的本机诊断包')
    sub.add_parser('panel', help='打开微光控制台')
    sub.add_parser('uninstall', help='卸载登录自启，保留数据')
    export = sub.add_parser('export', help='导出可迁移安装包')
    export.add_argument('destination')
    export.add_argument('--include-factory-backup', action='store_true')
    args = ap.parse_args()
    loc = Locations()
    try:
        if args.action == 'install':
            install(loc, args)
        elif args.action == 'bind-bluetooth':
            bind_bluetooth(loc)
        elif args.action == 'transport':
            change_transport(loc,args.mode)
        elif args.action == 'pause':
            pause(loc)
        elif args.action == 'resume':
            resume(loc)
        elif args.action == 'restart':
            if owned(loc).get('paused'):
                raise RuntimeError('当前已暂停；请用 resume 主动恢复。')
            stop_loaded(loc)
            resume(loc)
        elif args.action == 'recover':
            from recovery import recover
            result = recover(loc, allow_resume=args.resume)
            if args.json:print(json.dumps(result, ensure_ascii=False))
            else:print('同步已恢复，机器人已确认。' if result['ok'] else '尚未恢复同步：'+result['outcome'])
        elif args.action == 'status':
            status(loc, args.json)
        elif args.action == 'diagnostics':
            owned(loc)
            from diagnostics import export_bundle
            result=export_bundle(loc,status(loc,emit=False))
            print(json.dumps(result,ensure_ascii=False))
        elif args.action == 'panel':
            owned(loc)
            panel=loc.root/'微光控制台.app'
            if not (panel/'Contents/MacOS/WeiguangPanel').is_file():
                raise RuntimeError('控制台尚未安装，请先运行 ./weiguang install 更新。')
            subprocess.run(['/usr/bin/open',str(panel)],check=True)
        elif args.action == 'uninstall':
            uninstall(loc)
        else:
            export_package(args.destination, args.include_factory_backup)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'微光：{exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
