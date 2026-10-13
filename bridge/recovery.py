"""仅重建微光后台连接；以新的设备回执判断恢复，保留绑定和机器人偏好。"""
import contextlib
import fcntl
import io
import os
from pathlib import Path
import subprocess
import time


def outcome(state, started, now=None):
    now=time.time() if now is None else now
    if not state.get('installed'):return 'not_installed'
    if state.get('paused'):return 'paused'
    bridge=state.get('bridge') or {}
    if not state.get('fresh') or not state.get('pid'):return 'service_unavailable'
    if bridge.get('updated_at',0)<started or bridge.get('connection')!='connected':return 'waiting_device'
    if bridge.get('device_supported') is False:return 'firmware_update_required'
    stamp=bridge.get('device_at',0)
    if not bridge.get('device') or bridge.get('device_error') or not (started<=stamp<=now and now-stamp<25):return 'waiting_device'
    if bridge.get('data_source')!='ok':return 'data_unavailable'
    return 'synced'


def recover(loc, allow_resume=False, timeout=18):
    import service
    loc.runtime.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock_path=loc.runtime/'recovery.lock'
    with lock_path.open('a+') as lock:
        os.chmod(lock_path,0o600)
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'ok':False,'outcome':'busy'}
        try:
            config=service.owned(loc)
            if config.get('paused') and not allow_resume:
                return {'ok':False,'outcome':'paused','state':service.status(loc,emit=False)}
            started=time.time()
            # 复用原管理入口，先释放旧连接，恢复路径不会创建第二个同步所有者。
            with contextlib.redirect_stdout(io.StringIO()):
                service.stop_loaded(loc)
                if service.owned(loc).get('paused') and not allow_resume:
                    return {'ok':False,'outcome':'paused','state':service.status(loc,emit=False)}
                service.resume(loc)
            deadline=time.monotonic()+timeout
            while True:
                state=service.status(loc,emit=False)
                current=outcome(state,started)
                if current in ('synced','paused','not_installed','data_unavailable','firmware_update_required') or time.monotonic()>=deadline:
                    return {'ok':current=='synced','outcome':current,'state':state}
                time.sleep(.4)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            return {'ok':False,'outcome':'recovery_failed'}
        finally:fcntl.flock(lock,fcntl.LOCK_UN)
