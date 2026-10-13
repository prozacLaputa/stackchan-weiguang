"""仅从可见聊天文本提取保守的表情线索；不调用模型、不保存正文。"""
import re

MOODS = {'idle', 'focus', 'thinking', 'curious', 'joy'}
DURATION = {'focus': 35, 'thinking': 35, 'curious': 16, 'joy': 8}


def visible_text(item):
    if item.get('type') != 'message':
        return ''
    role = item.get('role')
    if role not in ('user', 'assistant'):
        return ''
    if role == 'assistant' and (item.get('channel') or item.get('phase')) not in ('commentary', 'final', 'final_answer'):
        return ''  # 不读取推理、工具输出或未知类型消息。
    text = '\n'.join(c.get('text', '') for c in item.get('content', [])
                     if isinstance(c, dict) and c.get('type') in ('input_text', 'output_text'))
    if text.lstrip().startswith(('# AGENTS.md', '<environment_context>', '<external_codex_apps_open_page>',
                                  '<send_user_message_question_reply>')):
        return ''
    text = re.sub(r'<in-app-browser-context\b[^>]*>.*?</in-app-browser-context>', '', text, flags=re.S)
    text = re.sub(r'```.*?(?:```|$)', '', text, flags=re.S)
    text = re.sub(r'`[^`]*`', '', text)
    text = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith(('>', '|')))
    return text[:8000]


def classify(text):
    # 忽略设想、否定与讲解表情机制的句子，避免“比如遇到报错”让它一直疑惑。
    clauses = re.split(r'[。！？!?；;，,：:\n]', text.lower())
    clauses = [c.strip() for c in clauses if c.strip() and not re.search(
        r'比如|例如|假如|如果|当.*时|表情|触发|测试用例|不再|没有|并未|尚未|还没|不是|不会|未解决|不满意|不成功', c)]
    patterns = (
        ('curious', r'还是不行|不太对|没反应|报错了|出错了|失败了|卡住了|(?:仍然|还在|还是|又在).{0,6}(?:报错|失败|异常)|出现.{0,8}(?:报错|异常)|遇到.{0,8}(?:问题|报错)|\b(?:still broken|failed again|not working)\b'),
        ('joy', r'解决了|修好了|搞定了|成功了|太好了|很满意|已经满意|非常满意|测试通过|验证通过|已修复|问题已解决|\b(?:it works|tests passed|fixed it)\b'),
        ('thinking', r'为什么|怎么回事|分析一下|想一下|讨论.{0,8}方案|评估.{0,8}方案|(?:我|先|正在|开始).{0,8}(?:分析|思考|梳理|评估)|\b(?:thinking through|consider the tradeoffs)\b'),
        ('focus', r'(?:开始|继续|正在|我先|接下来|我会|先).{0,12}(?:实现|开发|编写|修复|调试|测试|编译|刷入|修改)|\b(?:implementing|compiling|running tests)\b'),
    )
    for mood, pattern in patterns:
        if any(re.search(pattern, clause) for clause in clauses):
            return mood
    return None


class ExpressionTracker:
    def __init__(self):
        self.mood = 'idle'
        self.at = 0

    def accept(self, item, stamp):
        text = visible_text(item)
        mood = classify(text) if text else None
        if not mood or stamp <= 0 or stamp < self.at:
            return
        # 同一线索可以延续，切换至少间隔 4 秒；疑惑优先于刚刚的开心。
        if mood != self.mood and stamp - self.at < 4 and not (mood == 'curious' and self.mood == 'joy'):
            return
        self.mood, self.at = mood, stamp

    def current(self, now, state):
        if state in ('unknown', 'interrupted') or (state == 'done' and self.mood == 'focus'):
            return 'idle'
        if 0 <= now - self.at < DURATION.get(self.mood, 0):
            return self.mood
        return 'idle'

    def reset(self):
        self.mood, self.at = 'idle', 0
