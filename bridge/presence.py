"""只读取当前 Mac 会话的锁定/控制台状态，不读取屏幕、应用或输入内容。"""
import ctypes as C
import secrets
import sys
import time


def interpret(on_console, login_done, locked):
    if on_console is False or locked is True:return 'away'
    if on_console is True and login_done is True and locked in (False,None):return 'awake'
    return 'unknown'


class SessionReader:
    def __init__(self):
        self.cg=C.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
        self.cf=C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.cg.CGSessionCopyCurrentDictionary.argtypes=[];self.cg.CGSessionCopyCurrentDictionary.restype=C.c_void_p
        for name,args,rest in [('CFStringCreateWithCString',[C.c_void_p,C.c_char_p,C.c_uint32],C.c_void_p),
                               ('CFDictionaryGetValue',[C.c_void_p,C.c_void_p],C.c_void_p),
                               ('CFGetTypeID',[C.c_void_p],C.c_ulong),('CFBooleanGetTypeID',[],C.c_ulong),
                               ('CFBooleanGetValue',[C.c_void_p],C.c_bool),('CFRelease',[C.c_void_p],None)]:
            fn=getattr(self.cf,name);fn.argtypes=args;fn.restype=rest
    def __call__(self):
        data=self.cg.CGSessionCopyCurrentDictionary()
        if not data:return 'unknown'
        def boolean(name):
            key=self.cf.CFStringCreateWithCString(None,name.encode(),0x08000100)
            if not key:return None
            try:
                value=self.cf.CFDictionaryGetValue(data,key)
                if value and self.cf.CFGetTypeID(value)==self.cf.CFBooleanGetTypeID():return bool(self.cf.CFBooleanGetValue(value))
                return None
            finally:self.cf.CFRelease(key)
        try:
            # 锁定字段并非公开稳定契约；读取失败会降级。实际锁屏体验需单独核对。
            return interpret(boolean('kCGSSessionOnConsoleKey'),boolean('kCGSessionLoginDoneKey'),boolean('CGSSessionScreenIsLocked'))
        finally:self.cf.CFRelease(data)


class MacPresence:
    def __init__(self, reader=None, clock=time.monotonic):
        self.clock=clock;self.reader=reader;self.state='unknown';self.sampled=None
        self.token=0;self.token_until=0;self.last_greeting=None;self.away_since=0
        if self.reader is None and sys.platform=='darwin':
            try:self.reader=SessionReader()
            except (OSError,AttributeError):pass
    def snapshot(self):
        now=self.clock()
        if self.sampled is None or now-self.sampled>=1:
            try:next_state=self.reader() if self.reader else 'unknown'
            except (OSError,ValueError,TypeError):next_state='unknown'
            if next_state not in ('awake','away','unknown'):next_state='unknown'
            if next_state=='away' and self.state!='away':self.away_since=now
            if next_state=='awake' and self.state=='away' and now-self.away_since>=2 and (self.last_greeting is None or now-self.last_greeting>=60):
                self.token=secrets.randbelow(4294967295)+1;self.token_until=now+10;self.last_greeting=now
            if next_state!='awake':self.token_until=0
            self.state=next_state;self.sampled=now
        return self.state,self.token if now<self.token_until else 0
