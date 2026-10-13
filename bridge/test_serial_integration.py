"""真实伪串口 + 独立桥接进程，验证重连、退出与事件抑制，不操作机器人。"""
import datetime as dt
import json
import os
from pathlib import Path
import select
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest


class Device:
    def __init__(self):
        self.master, self.slave = os.openpty()
        self.name = os.ttyname(self.slave)
        self.packets = []
        self.halt = threading.Event()
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        buffer = b''
        while not self.halt.is_set():
            try:
                if not select.select([self.master], [], [], .1)[0]:
                    continue
                buffer += os.read(self.master, 4096)
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if line.startswith(b'SC5\t'):
                        fields=line.decode().split('\t');self.packets.append(fields[:3]+fields[8:])
                        os.write(self.master, b'ACK\t' + line.split(b'\t')[1] + b'\n')
                    elif line.startswith(b'DEVICE_INFO\t'):
                        # 旧固件兼容：不支持控制台也不能破坏既有任务同步。
                        os.write(self.master,b'ERROR\tcommand\n')
            except OSError:
                break

    def close(self):
        self.halt.set()
        self.thread.join(1)
        for fd in (self.master, self.slave):
            os.close(fd)


def wait_for(condition, timeout=12):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return
        time.sleep(.05)
    raise AssertionError('等待伪串口链路超时')


class SerialIntegrationTests(unittest.TestCase):
    def test_process_reconnect_snapshot_and_clean_shutdown(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            log = root/'rollout.jsonl'
            db = root/'state_5.sqlite'
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE threads(id TEXT,rollout_path TEXT,name TEXT,title TEXT,updated_at INTEGER,archived INTEGER,agent_path TEXT)')
                conn.execute('INSERT INTO threads VALUES(?,?,?,?,?,0,NULL)', ('task',str(log),'测试任务','',1))
            conn.close()
            def event(kind, turn):
                with log.open('a') as stream:
                    stream.write(json.dumps(dict(timestamp=dt.datetime.now(dt.timezone.utc).isoformat(), type='event_msg', payload=dict(type=kind, turn_id=turn)))+'\n')
            event('task_started', 'old')
            event('task_complete', 'old')
            device = Device()
            link = root/'serial'
            link.symlink_to(device.name)
            command = [sys.executable, str(Path(__file__).with_name('monitor.py')), '--port', str(link),
                       '--db', str(db), '--runtime-dir', str(root/'runtime'), '--thread', '']
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                wait_for(lambda: device.packets)
                self.assertEqual(device.packets[-1][6], '-')
                duplicate = subprocess.run(command, capture_output=True, timeout=5)
                self.assertNotEqual(duplicate.returncode, 0)
                self.assertIn('已有微光同步进程', duplicate.stderr.decode())
                event('task_started', 'new')
                event('task_complete', 'new')
                wait_for(lambda: any(packet[6] != '-' for packet in device.packets))
                first_event = device.packets[-1][6]
                device.close()
                device = Device()
                link.unlink()
                link.symlink_to(device.name)
                wait_for(lambda: device.packets)
                self.assertEqual(device.packets[-1][6], '-')
                event('task_started', 'after')
                event('task_complete', 'after')
                wait_for(lambda: any(packet[6] != '-' for packet in device.packets))
                self.assertNotEqual(device.packets[-1][6], first_event)
                state = json.loads((root/'runtime/status.json').read_text())
                self.assertEqual(state['connection'], 'connected')
                self.assertEqual(state['data_source'], 'ok')
                process.terminate()
                stdout, stderr = process.communicate(timeout=6)
                self.assertEqual(process.returncode, 0, stderr.decode())
                self.assertEqual(json.loads((root/'runtime/status.json').read_text())['connection'], 'stopped')
                self.assertNotIn('测试任务', (root/'runtime/bridge.log').read_text())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
                device.close()

if __name__ == '__main__':
    unittest.main()
