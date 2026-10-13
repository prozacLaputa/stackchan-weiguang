"""摘取当前轮可见的进展说明；不猜测工具阶段、不读取推理、不调用模型。"""
from completion_summary import summarize_completion

PROGRESS_TTL = 180


class ProgressTracker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.hint, self.at = '', 0

    def accept(self, item, stamp):
        if (item.get('type') != 'message' or item.get('role') != 'assistant'
                or (item.get('channel') or item.get('phase')) != 'commentary'
                or item.get('recipient') not in (None, 'all')
                or stamp <= 0 or stamp < self.at):
            return
        content = item.get('content')
        if not isinstance(content, list):
            return
        text = '\n'.join(c['text'] for c in content if isinstance(c, dict)
                         and c.get('type') == 'output_text' and isinstance(c.get('text'), str))
        # 引用和媒体描述不作为 Agent 自己的进展。
        text = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith(('>', '![')))
        excerpt = summarize_completion(text)
        self.hint = '进展：' + excerpt[len('摘录：'):] if excerpt else ''
        self.at = stamp

    def current(self, now, state):
        return self.hint if state == 'running' and 0 <= now - self.at < PROGRESS_TTL else ''
