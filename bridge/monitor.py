"""只读当前 Codex 会话，把生命周期状态通过 USB 发到 Chan。"""
import argparse
from contextlib import closing
import datetime as dt
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import time
from expression import ExpressionTracker, MOODS
from waiting_reason import clean_reason, summarize_question
from completion_summary import summarize_completion
from task_progress import ProgressTracker

# 让紧邻的排队续轮先到达；完成提醒只在主会话确实停下后发布。
COMPLETION_SETTLE_SECONDS = 1.0

class Tracker:
    def __init__(self):
        self.state = 'unknown'
        self.turn = None
        self.last_event = 0
        self.questions = {}
        self.completed_key = ''
        self.completed_at = 0
        self.wait_key = ''
        self.expression = ExpressionTracker()
        self.final_candidate = ''
        self.result_hint = ''
        self.progress = ProgressTracker()

    def accept_item(self, item):
        kind = item.get('type')
        if (kind == 'message' and item.get('role') == 'assistant'
                and (item.get('channel') or item.get('phase')) in ('final', 'final_answer')
                and self.state == 'running'):
            self.final_candidate = '\n'.join(c.get('text', '') for c in item.get('content', [])
                                             if isinstance(c, dict) and isinstance(c.get('text'), str))
        if kind == 'function_call':
            name = item.get('name', '').split('.')[-1]
            if name not in ('request_user_input', 'request_user_input_async'):
                return
            try:
                args = json.loads(item.get('arguments', '{}'))
                questions = args.get('questions') if isinstance(args, dict) else None
                count = len(questions) if isinstance(questions, list) else 0
            except (ValueError, TypeError):
                return
            call = item.get('call_id')
            if call and count:
                self.questions[call] = dict(kind=name, remaining=set(range(count)),
                                            summaries={i:summarize_question(q) for i,q in enumerate(questions)},
                                            accepted=name == 'request_user_input')
                if name == 'request_user_input':
                    self.wait_key = hashlib.sha256(call.encode()).hexdigest()[:16]
        elif kind == 'function_call_output':
            call = item.get('call_id')
            question = self.questions.get(call)
            if not question:
                return
            if question['kind'] == 'request_user_input':
                # 阻塞式问题的返回意味着已回答、取消或工具失败，均不再等待。
                self.questions.pop(call, None)
            else:
                try:
                    result = json.loads(item.get('output', '{}'))
                except (ValueError, TypeError):
                    result = None
                if isinstance(result, dict) and result.get('accepted') is True:
                    question['accepted'] = True
                    self.wait_key = hashlib.sha256(call.encode()).hexdigest()[:16]
                else:
                    self.questions.pop(call, None)
        elif kind == 'message' and item.get('role') == 'user':
            text = '\n'.join(c.get('text', '') for c in item.get('content', [])
                             if isinstance(c, dict))
            tag = '<send_user_message_question_reply>'
            if tag in text:
                try:
                    replies = json.loads(text.split(tag, 1)[1].split('</send_user_message_question_reply>', 1)[0])
                    for reply in replies:
                        name, call, index = json.loads(reply['questionItemId'])
                        if not isinstance(call, str) or not isinstance(index, int):
                            continue
                        question = self.questions.get(call)
                        if question and name == question['kind']:
                            question['remaining'].discard(index)
                            if not question['remaining']:
                                self.questions.pop(call, None)
                except (ValueError, KeyError, TypeError):
                    pass
            elif text.strip() and not text.lstrip().startswith(('<external_codex_apps_open_page>', '<environment_context>')):
                # 普通打字/语音也可能是回答或新指令；不让旧问题继续误报。
                self.questions.clear()
                self.progress.reset()

    def accept(self, record):
        stamp = record.get('timestamp', '')
        event_at = 0
        try:
            event_at = dt.datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()
            self.last_event = event_at
        except ValueError:
            pass
        if record.get('type') == 'response_item':
            self.expression.accept(record.get('payload', {}), event_at)
            item = record.get('payload', {})
            if self.state == 'running':
                self.progress.accept(item, event_at)
                if item.get('role') == 'assistant' and (item.get('channel') or item.get('phase')) in ('final', 'final_answer'):
                    self.progress.reset()
            self.accept_item(item)
            return
        if record.get('type') != 'event_msg':
            return
        p = record.get('payload', {})
        kind, turn = p.get('type'), p.get('turn_id')
        if kind == 'task_started':
            self.turn, self.state = turn, 'running'
            self.completed_key, self.completed_at = '', 0
            self.questions.clear()
            self.final_candidate = self.result_hint = ''
            self.progress.reset()
            # 用户消息可能略早于 task_started；只保留刚刚的当前输入线索。
            if not 0 <= event_at - self.expression.at <= 2:
                self.expression.reset()
        elif turn == self.turn or self.turn is None:
            if kind == 'task_complete':
                # 重复落盘不产生新的完成事件；已中断的轮次也不补报成功。
                if self.state in ('done', 'interrupted'):
                    return
                self.turn = turn
                self.state = 'done'
                self.progress.reset()
                self.result_hint = summarize_completion(p.get('last_agent_message') or self.final_candidate)
                self.final_candidate = ''
                # 等用户回应与完成互斥；后来回答问题也不补播旧完成。
                pending = any(q['accepted'] and q['remaining'] for q in self.questions.values())
                self.completed_key = '' if pending else hashlib.sha256(f'{turn}:{stamp}'.encode()).hexdigest()[:16]
                self.completed_at = self.last_event
            elif kind == 'turn_aborted':
                self.state = 'interrupted'
                self.completed_key, self.completed_at = '', 0
                self.progress.reset()
                self.final_candidate = self.result_hint = ''
                self.questions.clear()
                self.expression.reset()

    def current(self, now=None):
        if any(q['accepted'] and q['remaining'] for q in self.questions.values()):
            return 'needs_input'
        # 无新事件不能证明仍在运行；长工具调用同样保守标为待确认。
        if self.state == 'running' and (now or time.time()) - self.last_event > 300:
            return 'unknown'
        return self.state

    def notification_keys(self, now=None):
        now = time.time() if now is None else now
        pending = sorted(call for call, q in self.questions.items() if q['accepted'] and q['remaining'])
        waiting = self.wait_key if pending else ''
        # 旧完成记录只显示状态，不在恢复连接时补播成新提醒。
        completed = self.completed_key if (self.current(now) == 'done'
                    and COMPLETION_SETTLE_SECONDS <= now - self.completed_at <= 30) else ''
        return completed, waiting

    def waiting_reason(self):
        for question in reversed(list(self.questions.values())):
            if question['accepted'] and question['remaining']:
                index = min(question['remaining'])
                return question['summaries'].get(index, '待你在 Codex 回应')
        return ''

class Tail:
    def __init__(self, path):
        self.path = Path(path)
        self.offset = 0
        self.identity = None
        self.tracker = Tracker()

    def poll(self):
        stat = self.path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if identity != self.identity or stat.st_size < self.offset:
            self.offset = max(0, stat.st_size - 2_000_000)
            if self.offset:
                with self.path.open('rb') as start:
                    start.seek(self.offset)
                    start.readline()
                    self.offset = start.tell()
            self.tracker = Tracker()
            self.identity = identity
        if stat.st_size==self.offset:
            return self.tracker.current()
        with self.path.open('rb') as f:
            f.seek(self.offset)
            while raw := f.readline():
                if not raw.endswith(b'\n'):
                    break  # 下轮重读写了一半的 JSON。
                self.offset = f.tell()
                try:
                    self.tracker.accept(json.loads(raw))
                except (ValueError, UnicodeDecodeError):
                    continue
        return self.tracker.current()

def metadata(db, thread):
    with closing(sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as conn:
        row = conn.execute('SELECT rollout_path, name, title FROM threads WHERE id=?', (thread,)).fetchone()
    if not row:
        raise RuntimeError('找不到指定会话')
    return row[0], row[1] or row[2] or '未命名任务'

def packet(seq, state, title):
    title = ' '.join(title.split())[:60]
    return f'SC1\t{seq}\t{state}\t{title}\n'.encode('utf-8')

def main_session_source(source, thread_source):
    """旧版子代理路径并不完整；审批代理也可能没有 agent_path。"""
    if thread_source in ('subagent', 'guardian_review'):
        return False
    if source is None or source == '':
        return True  # 较旧数据库没有来源字段，仍保留既有路径筛选。
    if not isinstance(source, str):
        return False
    source = source.strip()
    # Codex 的结构化 source 是内部代理来源；损坏的结构化元数据也不冒充主会话。
    return not (source.startswith(('{', '[')) or source.lower() in ('subagent', 'guardian', 'guardian_review'))


def recent_tasks(db, preferred):
    with closing(sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as conn:
        columns = {r[1] for r in conn.execute('PRAGMA table_info(threads)')}
        source = 'source' if 'source' in columns else 'NULL'
        thread_source = 'thread_source' if 'thread_source' in columns else 'NULL'
        conn.create_function('weiguang_main_session', 2, main_session_source)
        # 必须先过滤再 LIMIT，避免后台检查挤掉真正活跃的主会话。
        rows = conn.execute(f"SELECT id, rollout_path, COALESCE(NULLIF(name,''),title), updated_at FROM threads WHERE archived=0 AND agent_path IS NULL AND weiguang_main_session({source},{thread_source}) ORDER BY updated_at DESC, id ASC LIMIT 24").fetchall()
    return rows

def choose_tasks(tasks, preferred, limit=8):
    # 自动显示最近活跃的 Top 8；preferred 仅保留旧调用兼容，不再固定会话。
    # 同一时间更新的任务按稳定 ID 排序，避免无新活动时列表来回跳动。
    ranked = sorted(tasks, key=lambda t: (-t['updated'], t['id']))
    return ranked[:limit]

def task_fields(task):
    return [task['id'], task['state'], ' '.join(task['title'].split())[:60],
                       task.get('done_key') or '-', task.get('wait_key') or '-',
                       task.get('mood') if task.get('mood') in MOODS else 'idle']

def batch_packet(seq, tasks):
    fields = ['SC4', str(seq), str(len(tasks))]
    for task in tasks:
        fields.extend(task_fields(task))
    return ('\t'.join(fields) + '\n').encode('utf-8')

def sync_packet(seq, tasks, data_ok, seconds, good_seconds, age, baseline, with_reasons=False, with_results=False, with_progress=False):
    fields = ['SC8' if with_progress else 'SC7' if with_results else 'SC6' if with_reasons else 'SC5', str(seq), str(len(tasks)),
                   'ok' if data_ok else 'unavailable', str(seconds),
                   str(good_seconds) if good_seconds is not None else '-',
                   str(max(0, min(604800, int(age)))), '1' if baseline else '0']
    for task in tasks:
        fields.extend(task_fields(task))
        if with_reasons or with_results or with_progress:
            reason = clean_reason(task.get('wait_reason')) if data_ok and task['state']=='needs_input' else ''
            if (with_results or with_progress) and data_ok and task['state']=='done':
                reason = clean_reason(task.get('result_hint'))
            if with_progress and data_ok and task['state']=='running':
                reason = clean_reason(task.get('progress_hint'))
            fields.append(reason or '-')
    return ('\t'.join(fields) + '\n').encode('utf-8')


def main():
    from runtime import TaskSource, run
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--thread', default=os.environ.get('CODEX_THREAD_ID'), help='兼容旧启动参数；当前统一按最近活跃自动选取，不固定会话')
    ap.add_argument('--port', default='auto')
    ap.add_argument('--transport', choices=('usb','ble','auto'), default='usb')
    ap.add_argument('--ble-device')
    ap.add_argument('--ble-key-file')
    ap.add_argument('--ble-helper')
    ap.add_argument('--serial-number', help='绑定机器人的 USB 序列号，不依赖端口名称')
    ap.add_argument('--codex-home', type=Path, default=Path(os.environ.get('CODEX_HOME', Path.home()/'.codex')))
    ap.add_argument('--db', type=Path, help='可选：明确指定会话数据库，否则自动发现最新版本')
    ap.add_argument('--runtime-dir', type=Path, default=Path(__file__).resolve().parent.parent/'.runtime')
    ap.add_argument('--once', action='store_true', help='只读状态，不打开 USB')
    args = ap.parse_args()
    source = TaskSource(args.codex_home, args.db, args.thread)
    if args.once:
        print(json.dumps(source.snapshot(), ensure_ascii=False))
        return
    run(source, args.runtime_dir, args.port, args.serial_number, args.transport, args.ble_device, args.ble_key_file, args.ble_helper)

if __name__ == '__main__':
    main()
