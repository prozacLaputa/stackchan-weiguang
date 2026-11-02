"""只解析用户本轮完整识别文字；不读取模型回复，不执行操作。"""
import re
from control import valid_note_text


def duration_number(text):
    if text.isascii() and text.isdigit():return int(text) if len(text)<=3 else None
    digits={'零':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
    if text in digits:return digits[text]
    if '百' in text:
        if text.count('百')!=1:return None
        head,tail=text.split('百')
        if head not in digits or not digits[head]:return None
        tail=tail.removeprefix('零');rest=duration_number(tail) if tail else 0
        return digits[head]*100+rest if rest is not None and rest<100 else None
    if '十' in text and text.count('十')==1:
        head,tail=text.split('十')
        if (head and (head not in digits or not digits[head])) or (tail and (tail not in digits or not digits[tail])):return None
        return (digits[head] if head else 1)*10+(digits[tail] if tail else 0)
    return None


def parse_voice_command(text):
    if not isinstance(text,str) or not 1<=len(text)<=2000:return None
    value=text.strip().strip('。.!！?？')
    # 问句、引用、否定和复合句不会因为包含关键词而执行。
    if text.rstrip().endswith(('?','？')):return None
    value=re.sub(r'^(?:微光|小微光)[，,、\s]*','',value)
    value=re.sub(r'^(?:请帮我|麻烦你帮我|麻烦帮我|请你帮我|帮我|请你|请|麻烦你)[，,\s]*','',value)
    note=re.fullmatch(r'(?:(?:记|寄)(?:一个|1个|个|一条|1条|条)?便签|写(?:一个|1个|个|一条|1条|条)?便签|贴(?:一个|1个|个|一张|1张|张)?便签)[：:，,\s]*(.+)',value)
    if note:
        content=note[1].strip().strip('“”「」')
        if not valid_note_text(content):return {'kind':'help','code':'note_length'}
        return {'kind':'note','text':content}
    compact=re.sub(r'\s+','',value)
    # 来自实际原厂STT的有界转写差异；只在完整指令末尾识别，不模糊匹配整句。
    timer=r'(?:番茄钟|番茄中|番茄鐘|专注计时)'
    number=r'[0-9零一二三四五六七八九十百两]+'
    start=re.fullmatch(r'(?:开始|启动|开)(?:一个|1个|个)?(?:(半小时|(?:'+number+r')(?:分钟|个?小时(?:半)?))(?:的)?)?'+timer,compact)
    if start:
        duration=start[1]
        if duration is None or duration=='半小时':minutes=30
        else:
            match=re.fullmatch('('+number+r')(分钟|个?小时)(半)?',duration)
            count=duration_number(match[1]);minutes=None if count is None else count*(60 if match[2].endswith('小时') else 1)+(30 if match[3] else 0)
        if minutes is None or not 1<=minutes<=240:return {'kind':'help','code':'focus_duration'}
        return {'kind':'focus','operation':'start','minutes':minutes}
    for verbs,operation in [('暂停','pause'),('继续|恢复','resume'),('结束|停止','stop')]:
        if re.fullmatch(r'(?:'+verbs+r')(?:一下|1下)?'+timer,compact):
            return {'kind':'focus','operation':operation}
    return None


class LocalVoiceCommand(Exception):
    def __init__(self,command):
        super().__init__('local_voice_command')
        self.command=command
