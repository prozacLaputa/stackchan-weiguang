"""从原生问题卡片取短提示；不读取答案、聊天正文或调用模型。"""
import re

MAX_REASON_CHARS = 32


def clean_reason(value, limit=MAX_REASON_CHARS):
    if not isinstance(value, str):
        return ''
    value = re.sub(r'```.*?(?:```|$)', '…', value[:4096], flags=re.S)
    value = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', value)
    value = re.sub(r'https?://\S+', '链接', value)
    value = re.sub(r'`[^`]*`', '…', value)
    value = re.sub(r'[\x00-\x1f\x7f]', ' ', value)
    value = ' '.join(value.split()).strip(' #*')
    return value if len(value) <= limit else value[:limit-1].rstrip() + '…'


def summarize_question(question):
    if not isinstance(question, dict):
        return '待你在 Codex 回应'
    header = clean_reason(question.get('header'), 12)
    generic = {'问题', '选择', '选项', '确认', '下一步', 'Question', 'Choice'}
    if header and header not in generic:
        options = question.get('options')
        prefix = '待选择：' if isinstance(options,list) and len(options)>1 else '待答：'
        return clean_reason(prefix + header)
    raw = question.get('question') or question.get('title')
    raw = clean_reason(raw, 512)
    if not raw:
        return '待你在 Codex 回应'
    clauses = [part.strip() for part in re.split(r'(?<=[。！？!?；])\s*', raw) if part.strip()]
    questions = [part for part in clauses if part.endswith(('？', '?'))]
    requests = [part for part in clauses if re.match(r'^(现在)?(请|帮我|麻烦)', part)]
    # 优先保留真正的问句或操作要求，避免只显示“新版本已刷好”等背景。
    body = questions[-1] if questions else requests[0] if requests else clauses[0]
    body = body.strip(' 。！？!?；')
    return clean_reason('待答：' + body) if body else '待你在 Codex 回应'
