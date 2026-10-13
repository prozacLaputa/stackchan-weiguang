"""摘录本轮最终回复，不把本轮结束判定为项目成功，不调用模型。"""
import re
from waiting_reason import clean_reason


def summarize_completion(value):
    if not isinstance(value, str):
        return ''
    text = value[:16384]
    text = re.sub(r'<oai-mem-citation>.*?(?:</oai-mem-citation>|$)', '', text, flags=re.S)
    text = re.sub(r'```.*?(?:```|$)', '', text, flags=re.S)
    text = re.sub(r'::[\w-]+\{[^}]*\}', '', text)
    for line in text.splitlines():
        line = line.strip()
        # 跳过结构性标题和表格，优先保留回复正文中的第一句。
        if not line or line.startswith(('#', '|', '![', '<')):
            continue
        line = re.sub(r'^\s*(?:[-*+] |\d+[.)] )', '', line)
        line = re.sub(r'\*\*([^*]+)\*\*|__([^_]+)__', lambda m: m[1] or m[2], line)
        line = clean_reason(line, 512).strip(' ：:')
        if len(line) < 3 or line in ('总结', '结果', '改动', '验证', '下一步'):
            continue
        sentence = re.split(r'(?<=[。！？!?])\s*', line, maxsplit=1)[0]
        return clean_reason('摘录：' + sentence)
    return ''
