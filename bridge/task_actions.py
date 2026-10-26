"""只读解析仍待回应的本地会话；跳转由原生控制台执行，不接管或回复任务。"""
import json
import math
import re
from pathlib import Path
import sys
import uuid
from waiting_reason import clean_reason


def valid_thread_id(value):
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value.lower() and len(value) == 36
    except ValueError:
        return False


def pending_tasks(tasks):
    return [dict(id=t['id'], title=clean_reason(t.get('title'), 80) or '未命名任务',
                 reason=clean_reason(t.get('wait_reason')) or '待你在 Codex 回应')
            for t in tasks[:8] if t.get('state') == 'needs_input' and valid_thread_id(t.get('id'))]


def completion_events(tasks, now):
    """仅供本机可选语音提醒：明确完成、30秒内、Top8；不携带回复或结果正文。"""
    events = []
    for task in tasks[:8]:
        stamp, key = task.get('completed_at'), task.get('done_key')
        if (task.get('state') != 'done' or not valid_thread_id(task.get('id'))
                or not isinstance(key, str) or not re.fullmatch('[0-9a-f]{16}', key)
                or isinstance(stamp, bool) or not isinstance(stamp, (int, float))
                or not math.isfinite(stamp) or not 0 <= now - stamp <= 30):
            continue
        events.append(dict(id=task['id'], title=clean_reason(task.get('title'), 80) or '未命名任务',
                           key=key, completed_at=stamp))
    return events


def resolve_pending(source, thread_id):
    if not valid_thread_id(thread_id):
        return dict(ok=False, error='invalid_thread')
    # 点击时重新读会话，避免旧卡片跳向已经回答或移出 Top 8 的任务。
    if not any(t['id'] == thread_id for t in pending_tasks(source.snapshot())):
        return dict(ok=False, error='no_longer_waiting')
    return dict(ok=True, thread_id=thread_id)


def main():
    try:
        from service import Locations, owned
        from runtime import TaskSource
        if len(sys.argv) != 2:
            raise ValueError('invalid_request')
        config = owned(Locations())
        if config.get('paused'):
            result = dict(ok=False, error='paused')
        else:
            result = resolve_pending(TaskSource(config['codex_home']), sys.argv[1])
    except Exception:
        result = dict(ok=False, error='data_unavailable')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()


def open_pending(source, thread_id, presence, opener=None):
    """机器人手势只请求打开；重新确认当前 Top8 待答和已解锁状态。"""
    import subprocess
    if presence != 'awake':
        return 'locked'
    try:
        result = resolve_pending(source, thread_id)
        if not result['ok']:
            return 'stale'
        url = f'codex://threads/{thread_id.lower()}?hostId=local'
        if opener is None:
            # 固定程序和 URL scheme，不接受路径、命令或额外参数。
            subprocess.run(['/usr/bin/open', url], check=True, timeout=2,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            opener(url)
        return 'opened'  # LaunchServices 接受请求，不代表用户已经阅读。
    except Exception:
        return 'failed'


def parse_action(raw, seq):
    parts = raw.decode('ascii').strip().split('\t')
    if len(parts) != 4 or parts[:2] != ['ACTION', str(seq)]:
        raise ValueError('invalid_action_reply')
    if parts[2:] == ['0', '-']:
        return None
    if not parts[2].isdigit() or not 0 < int(parts[2]) <= 4294967295 or not valid_thread_id(parts[3]):
        raise ValueError('invalid_action_reply')
    return int(parts[2]), parts[3]


def parse_action_request(raw, seq):
    """旧四字段仍只打开待回应；新 task 范围用于真实卡片长按。"""
    parts=raw.decode('ascii').strip().split('\t')
    scope='waiting'
    if len(parts)==5:
        if parts[4]!='task':raise ValueError('invalid_action_scope')
        scope='task'
        parts=parts[:4]
    event=parse_action('\t'.join(parts).encode('ascii'),seq)
    if event is None:
        if scope!='waiting':raise ValueError('empty_task_action')
        return None
    return (*event,scope)


def open_visible(source, thread_id, presence, opener=None):
    """打开当前 Top 8 中的会话，不根据状态限制导航；不发送回复或批准。"""
    import subprocess
    if presence!='awake':return 'locked'
    if not valid_thread_id(thread_id):return 'stale'
    try:
        if not any(t.get('id')==thread_id for t in source.snapshot()[:8]):return 'stale'
        url=f'codex://threads/{thread_id.lower()}?hostId=local'
        if opener is None:
            subprocess.run(['/usr/bin/open',url],check=True,timeout=2,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:opener(url)
        return 'opened'
    except Exception:return 'failed'
