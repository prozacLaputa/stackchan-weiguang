"""只解析用户本轮完整识别文字；不读取模型回复，不执行操作。"""
import re
from control import valid_note_text


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
    start=re.fullmatch(r'(?:开始|启动|开)(?:一个|1个|个)?(?:(十五|二十五|四十五|[0-9一二三四五六七八九十两半]+)分钟(?:的)?)?'+timer,compact)
    if start:
        duration=start[1] or '25'
        minutes={'十五':15,'二十五':25,'四十五':45,'15':15,'25':25,'45':45}.get(duration)
        if minutes is None:return {'kind':'help','code':'focus_duration'}
        return {'kind':'focus','operation':'start','minutes':minutes}
    for verbs,operation in [('暂停','pause'),('继续|恢复','resume'),('结束|停止','stop')]:
        if re.fullmatch(r'(?:'+verbs+r')(?:一下|1下)?'+timer,compact):
            return {'kind':'focus','operation':operation}
    return None


class LocalVoiceCommand(Exception):
    def __init__(self,command):
        super().__init__('local_voice_command')
        self.command=command
