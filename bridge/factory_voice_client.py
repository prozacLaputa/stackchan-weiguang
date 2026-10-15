"""一次原厂问答：stdin短文本或有界麦克风PCM，stdout单声道48kHz float PCM；不含播放器或录音器。"""
import base64
import binascii
import ctypes
import fcntl
import json
import math
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unicodedata
from array import array
from contextlib import contextmanager

ROOT=Path(__file__).resolve().parent.parent
STAGE='starting'
sys.path.insert(0,str(ROOT/'checks'))

from factory_voice_identity import read_identity, summary
from factory_voice_probe import Mqtt, handle_capabilities, text_probe
from voice_commands import parse_voice_command, LocalVoiceCommand


def opus_packets(data):
    offset,pending,packets=0,bytearray(),[]
    while offset<len(data):
        if len(data)-offset<27 or data[offset:offset+5]!=b'OggS\0':
            raise ValueError('invalid_ogg')
        count=data[offset+26]
        lacing=data[offset+27:offset+27+count]
        if len(lacing)!=count: raise ValueError('invalid_lacing')
        cursor=offset+27+count
        for length in lacing:
            if cursor+length>len(data): raise ValueError('invalid_ogg_body')
            pending.extend(data[cursor:cursor+length]);cursor+=length
            if length<255: packets.append(bytes(pending));pending.clear()
        offset=cursor
    if pending or len(packets)<3 or not packets[0].startswith(b'OpusHead') or packets[0][9]!=1 or not packets[1].startswith(b'OpusTags'):
        raise ValueError('invalid_mono_opus')
    if not 1<=len(packets[2:])<=501: raise ValueError('input_too_long')
    return packets[2:]


class OpusDecoder:
    def __init__(self,library,pcm_sink=None):
        self.lib=ctypes.CDLL(library)
        self.lib.opus_decoder_create.argtypes=[ctypes.c_int32,ctypes.c_int,ctypes.POINTER(ctypes.c_int)]
        self.lib.opus_decoder_create.restype=ctypes.c_void_p
        self.lib.opus_decoder_destroy.argtypes=[ctypes.c_void_p]
        self.lib.opus_decode_float.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int32,ctypes.POINTER(ctypes.c_float),ctypes.c_int,ctypes.c_int]
        self.lib.opus_decode_float.restype=ctypes.c_int
        error=ctypes.c_int()
        self.state=self.lib.opus_decoder_create(48000,1,ctypes.byref(error))
        if not self.state or error.value: raise ValueError('decoder_create')
        self.last=None;self.output=bytearray();self.gaps=0;self.duplicates=0;self.pcm_sink=pcm_sink;self.frame_samples=0;self.concealed=0
    def add(self,sequence,packet):
        if self.last is not None:
            if sequence<=self.last:self.duplicates+=1;return
            if sequence!=self.last+1:
                self.gaps+=sequence-self.last-1
                # 乱序队列必须先补偿获准的小缺口，不能直接跳着解码。
                raise ValueError('audio_packet_gap')
        if len(packet)>4096:raise ValueError('audio_packet_size')
        self.decode(sequence,packet,5760)
    def conceal(self,missing):
        # 原厂60ms包：每次最多120ms、每条回复最多360ms；严重缺失仍停止。
        if self.last is None or self.frame_samples!=2880 or not 1<=missing<=2 or self.concealed+missing>6:
            raise ValueError('audio_packet_gap')
        for _ in range(missing):
            self.decode(self.last+1,None,self.frame_samples)
            self.gaps+=1;self.concealed+=1
    def decode(self,sequence,packet,frame_size):
        buffer=(ctypes.c_float*5760)()
        count=self.lib.opus_decode_float(self.state,packet,len(packet) if packet is not None else 0,buffer,frame_size,0)
        if count<=0:raise ValueError('decode_failed')
        pcm=ctypes.string_at(buffer,count*4)
        if len(self.output)+len(pcm)>48000*45*4:raise ValueError('reply_too_long')
        if any(not math.isfinite(v) or abs(v)>1 for v in buffer[:count]):raise ValueError('invalid_audio_samples')
        self.output.extend(pcm);self.last=sequence;self.frame_samples=count
        if self.pcm_sink is not None:self.pcm_sink(pcm)
    def close(self):
        if self.state:self.lib.opus_decoder_destroy(self.state);self.state=None


def command(args,timeout):
    child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        if child.wait(timeout=timeout)!=0:raise ValueError('input_generation_failed')
    finally:
        if child.poll() is None:child.kill();child.wait()


def cancelled(*_):raise InterruptedError('cancelled')


def sound_options(request):
    values=[]
    for name,default,low,high in (('rate',1.0,0.8,1.25),('pitch',0.0,-2.0,2.0)):
        value=request.get(name,default)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError('invalid_sound_options')
        values.append(float(value))
    return tuple(values)


def shape_audio(pcm,ffmpeg,rate,pitch):
    # 原声逐字节直通；本地声音风格不改变云端角色。整个回复仍只在内存。
    if rate==1.0 and pitch==0.0:return pcm
    factor=2**(pitch/12)
    filters=f'asetrate={48000*factor:.6f},aresample=48000,atempo={rate/factor:.8f}'
    child=subprocess.Popen([ffmpeg,'-hide_banner','-loglevel','error','-f','f32le','-ar','48000','-ac','1','-i','pipe:0',
                            '-af',filters,'-t','60','-f','f32le','-ar','48000','-ac','1','pipe:1'],
                           stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    try:
        data,_=child.communicate(pcm,timeout=15)
        if child.returncode!=0 or not data or len(data)%4 or len(data)>48000*60*4:raise ValueError('sound_processing_failed')
        samples=array('f');samples.frombytes(data)
        if any(not math.isfinite(v) for v in samples):raise ValueError('sound_processing_failed')
        # 重采样的轻微过冲有界压回，避免拒播或非有限样本进入音频线程。
        peak=max(1.0,max(abs(v) for v in samples))
        if peak>1:samples=array('f',(v/peak for v in samples))
        return samples.tobytes()
    finally:
        if child.poll() is None:child.kill();child.wait()


def input_upload_interval_ms(packet_count,requested=None):
    return requested if requested is not None else (60 if packet_count<=30 else 15)


@contextmanager
def factory_session(path=None,timeout=3):
    # 被取消的后台问候仍需完成goodbye/close；新请求先等它释放身份。
    # flock随进程退出释放，不依据PID或残留文件猜测是否仍在运行。
    path=path or ROOT/'.runtime/factory-voice-session.lock'
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_RDWR|os.O_CREAT,0o600)
    try:
        os.fchmod(fd,0o600)
        deadline=time.monotonic()+timeout
        while True:
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic()>=deadline:raise ValueError('previous_session_busy')
                time.sleep(0.05)
        yield
    finally:os.close(fd)


class SubtitleEmitter:
    """字幕只走显式开启的内存管道；报告不携带原文。"""
    def __init__(self,sink):self.sink=sink;self.count=0;self.characters=0
    def __call__(self,text):
        if self.sink is None or not isinstance(text,str) or self.count>=64:return
        text=''.join(c for c in text if ord(c)>=32 and ord(c)!=127 or c in '\n\t').strip()
        if not text or len(text)>2000 or self.characters+len(text)>6000:return
        self.count+=1;self.characters+=len(text)
        self.sink({'event':'subtitle','sequence':self.count,'text':text})


class NoticeSpeechCheck:
    """任务提醒只能播放预定文案；字幕核对不等同独立的音频转写验证。"""
    @staticmethod
    def normalized(text):
        # 只容忍标点和空白；不做模糊匹配、同义改写或大小写替换。
        return ''.join(c for c in unicodedata.normalize('NFC',text)
                       if not c.isspace() and not unicodedata.category(c).startswith('P'))
    def __init__(self,expected):
        if not isinstance(expected,str) or not 1<=len(expected)<=120 or any(ord(c)<32 for c in expected):
            raise ValueError('invalid_expected_speech')
        self.expected=self.normalized(expected);self.received=''
        if not self.expected:raise ValueError('invalid_expected_speech')
    def __call__(self,text):
        if not isinstance(text,str) or len(text)>2000:raise ValueError('notice_text_mismatch')
        self.received+=self.normalized(text)
        if not self.expected.startswith(self.received):raise ValueError('notice_text_mismatch')
    def finish(self):
        if self.received!=self.expected:raise ValueError('notice_text_mismatch')


MAX_REQUEST_BYTES=4*1024*1024
PCM_RATES=(8000,16000,24000,32000,44100,48000)


def input_payload(request):
    if not isinstance(request,dict):raise ValueError('invalid_text')
    if 'audio_pcm16' not in request:
        text=request.get('text','')
        if not isinstance(text,str) or not 1<=len(text.strip())<=120 or any(ord(c)<32 for c in text):raise ValueError('invalid_text')
        return text,None,None
    # 两种输入互斥，拒绝路径/URL、格式猜测及无限录音。
    value=request['audio_pcm16'];rate=request.get('sample_rate')
    if 'text' in request or type(rate) is not int or rate not in PCM_RATES or not isinstance(value,str) or len(value)>3840000:
        raise ValueError('invalid_microphone_input')
    try:pcm=base64.b64decode(value,validate=True)
    except (ValueError,binascii.Error):raise ValueError('invalid_microphone_input') from None
    if len(pcm)%2 or not rate*2/3<=len(pcm)<=rate*2*30:raise ValueError('invalid_microphone_input')
    return None,pcm,rate


def microphone_packets(pcm,rate,ffmpeg):
    child=subprocess.Popen([ffmpeg,'-hide_banner','-loglevel','error','-f','s16le','-ar',str(rate),'-ac','1','-i','pipe:0',
        '-ar','16000','-ac','1','-c:a','libopus','-application','voip','-frame_duration','60','-b:a','24k','-f','ogg','pipe:1'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    try:
        ogg,_=child.communicate(pcm,timeout=10)
        if child.returncode!=0 or len(ogg)>256000:raise ValueError('input_generation_failed')
        return opus_packets(ogg)
    finally:
        if child.poll() is None:child.kill();child.wait()


class TranscriptEmitter:
    def __init__(self,sink):self.sink=sink;self.sent=False
    def __call__(self,text):
        if self.sink is None or self.sent or not isinstance(text,str):return
        text=''.join(c for c in text if ord(c)>=32 and ord(c)!=127 or c in '\n\t').strip()
        if not text or len(text)>2000:return
        self.sent=True;self.sink({'event':'transcript','text':text})


def run(request,pcm_sink=None,event_sink=None):
    global STAGE
    STAGE='waiting_previous_session'
    with factory_session():
        return run_exclusive(request,pcm_sink,event_sink)


def run_exclusive(request,pcm_sink=None,event_sink=None):
    global STAGE
    STAGE='validating_input'
    text,microphone_pcm,microphone_rate=input_payload(request)
    notice=NoticeSpeechCheck(request['expected_speech']) if 'expected_speech' in request else None
    if notice is not None and microphone_pcm is not None:raise ValueError('invalid_expected_speech')
    rate,pitch=sound_options(request)
    stream=request.get('stream',False)
    upload_ms=request.get('upload_interval_ms')
    input_guard_ms=request.get('input_guard_ms',180)
    subtitle_events=request.get('subtitle_events',False)
    transcript_events=request.get('transcript_events',False)
    local_commands=request.get('local_commands',False)
    if not isinstance(local_commands,bool) or (local_commands and (microphone_pcm is None or not transcript_events or event_sink is None)):
        raise ValueError('invalid_stream_options')
    if not isinstance(subtitle_events,bool) or not isinstance(transcript_events,bool):raise ValueError('invalid_stream_options')
    if not isinstance(stream,bool) or ('upload_interval_ms' in request and (type(upload_ms) is not int or upload_ms not in (15,30,60))):raise ValueError('invalid_stream_options')
    if type(input_guard_ms) is not int or input_guard_ms not in (0,180):raise ValueError('invalid_stream_options')
    # 提醒先收完整再核对；即使调用方误传stream=True也绝不提前输出音频或正文。
    streaming=notice is None and stream and rate==1 and pitch==0 and pcm_sink is not None
    subtitles=SubtitleEmitter(event_sink if subtitle_events and notice is None else None)
    transcript=TranscriptEmitter(event_sink if transcript_events and microphone_pcm is not None else None)
    # 生成文件仅供本机编码，离开with即删除；绝不通过say/ffmpeg直接播放。
    ffmpeg=request.get('ffmpeg','/opt/homebrew/bin/ffmpeg')
    libopus=request.get('libopus','/opt/homebrew/lib/libopus.dylib')
    client=None;decoder=None
    report={'ok':False,'audio_output_created':False,'microphone_opened':False,'device_commands_sent':False,'role_modified':False,'activation_attempted':False,'events':[]}
    started=time.monotonic()
    try:
        STAGE='generating_input'
        if microphone_pcm is not None:
            packets=microphone_packets(microphone_pcm,microphone_rate,ffmpeg)
            report['input_kind']='microphone'
            report['input_duration_seconds']=round(len(microphone_pcm)/(microphone_rate*2),3)
            microphone_pcm=None
        else:
            with tempfile.TemporaryDirectory(prefix='weiguang-voice-') as temp:
                aiff=str(Path(temp)/'input.aiff');ogg=str(Path(temp)/'input.ogg')
                command(['/usr/bin/say','-v','Tingting','-o',aiff,text],20)
                command([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',aiff,'-ar','16000','-ac','1','-c:a','libopus','-application','voip','-frame_duration','60','-b:a','24k',ogg],10)
                packets=opus_packets(Path(ogg).read_bytes())
            report['input_kind']='text'
        upload_ms=input_upload_interval_ms(len(packets),upload_ms)
        report['upload_interval_ms']=upload_ms
        report['input_ready_seconds']=round(time.monotonic()-started,3)
        STAGE='reading_original_identity'
        identity=read_identity()
        if not summary(identity)['bound_device_matches_mqtt_client']:raise ValueError('device_mismatch')
        STAGE='connecting_factory'
        client=Mqtt(identity['mqtt'])
        if client.connect()!=0:raise ValueError('original_identity_rejected')
        report['connected_seconds']=round(time.monotonic()-started,3)
        client.subscribe()
        client.publish({'type':'hello','version':3,'transport':'udp','features':{'mcp':False},'audio_params':{'format':'opus','sample_rate':16000,'channels':1,'frame_duration':60}})
        STAGE='waiting_hello'
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            message=client.message()
            if not isinstance(message,dict):continue
            if message.get('type') in ('activation','activate') or 'activation' in message or 'activation_code' in message:raise ValueError('activation_required')
            handle_capabilities(client,message,report)
            if message.get('type')!='hello':continue
            client.session=message.get('session_id')
            params=message.get('audio_params',{})
            if not client.session or message.get('transport')!='udp' or params.get('format')!='opus' or params.get('channels')!=1:raise ValueError('unsupported_audio')
            def receive_pcm(pcm):
                report.setdefault('first_audio_seconds',round(time.monotonic()-started,3))
                if notice is not None and len(decoder.output)>48000*12*4:raise ValueError('reply_too_long')
                if streaming:pcm_sink(pcm)
            decoder=OpusDecoder(libopus,pcm_sink=receive_pcm)
            STAGE='receiving_audio'
            classified=not local_commands
            early_subtitles=[]
            def route_subtitle(value):
                if classified:subtitles(value)
                else:
                    if len(early_subtitles)>=64 or not isinstance(value,str) or len(value)>2000:raise ValueError('reply_too_long')
                    early_subtitles.append(value)
            def route_transcript(value):
                nonlocal classified
                transcript(value)
                if classified:return
                if not isinstance(value,str) or not value.strip():raise ValueError('recognition_timeout')
                command=parse_voice_command(value)
                if command is not None:raise LocalVoiceCommand(command)
                classified=True
                if streaming and decoder.output:pcm_sink(bytes(decoder.output))
                for value in early_subtitles:subtitles(value)
                early_subtitles.clear()
            # STT可能比音频晚到：识别前不把原厂的“好的”泄漏给播放器。
            def guarded_pcm(pcm):
                if classified:receive_pcm(pcm)
            decoder.pcm_sink=guarded_pcm
            try:
                text_probe(client,message,report,'listen-first',packets,decoder.add,upload_interval=upload_ms/1000,tail_wait=0.35,expected_text=text,gap_sink=decoder.conceal,input_guard=input_guard_ms/1000,subtitle_sink=notice if notice is not None else route_subtitle,transcript_sink=route_transcript)
            except LocalVoiceCommand as found:
                event_sink({'event':'local_command','command':found.command})
                report.update(ok=True,local_command=True,streaming=False,pcm_frames=0,elapsed_seconds=round(time.monotonic()-started,2))
                return b'',report
            if not classified:raise ValueError('recognition_timeout')
            if not report.get('tts_stopped') or not decoder.output:raise ValueError('reply_incomplete')
            if notice is not None:
                STAGE='verifying_notice'
                notice.finish()
                report['notice_text_verified']=True
            STAGE='shaping_audio'
            pcm=shape_audio(bytes(decoder.output),ffmpeg,rate,pitch)
            if notice is not None and len(pcm)>48000*12*4:raise ValueError('reply_too_long')
            report.update(ok=True,pcm_frames=len(pcm)//4,elapsed_seconds=round(time.monotonic()-started,2),packet_gaps=decoder.gaps,duplicates_discarded=decoder.duplicates,playback_rate=rate,playback_pitch=pitch,streaming=streaming)
            report['result']='factory_reply_received'
            report['subtitle_events']=subtitles.count
            # 原静音探针的固定口令断言不适用于普通聊天，不能混成失败结论。
            for name in ('expected_reply_observed','stt_expected_observed','text_audio_passed','speech_audio_passed'):
                report.pop(name,None)
            # 不写磁盘，不留下对话文本，stdout只交给受保护的原生播放器。
            return pcm,report
        raise ValueError('hello_timeout')
    except BaseException as error:
        # 失败也留下分段耗时／包计数；不留下正文、会话ID或认证字段。
        error.voice_metrics={k:report[k] for k in ('input_ready_seconds','connected_seconds','first_audio_seconds','input_upload_seconds','upload_interval_ms','input_guard_ms','capability_wait_seconds','reordered_audio_packets','missing_audio_packets','concealed_audio_packets','synthetic_speech_packets','audio_packets','stt_received','stt_seconds','tts_start_seconds','stt_input_matched','stt_input_similarity','stt_character_count','tts_started','tts_stopped','events') if k in report}
        raise
    finally:
        if decoder:decoder.close()
        if client:
            if client.socket:client.socket.settimeout(1)
            client.close()


def record(report):
    path=ROOT/'.runtime/voice/client-last.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(descriptor,'w') as handle:json.dump(report,handle,ensure_ascii=False,indent=2)


if __name__=='__main__':
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    try:
        raw=sys.stdin.buffer.read(MAX_REQUEST_BYTES+1)
        if len(raw)>MAX_REQUEST_BYTES:raise ValueError('request_too_large')
        def emit_pcm(pcm):
            sys.stdout.buffer.write(pcm);sys.stdout.buffer.flush()
        def emit_event(event):
            print(json.dumps(event,ensure_ascii=False),file=sys.stderr,flush=True)
        data,report=run(json.loads(raw),pcm_sink=emit_pcm,event_sink=emit_event)
        if not report['streaming']:emit_pcm(data)
        # 以下落盘诊断不含原文；字幕只通过显式开启的内存事件管道发送。
        record(report)
        print(json.dumps(report,ensure_ascii=False),file=sys.stderr)
    except BaseException as error:
        allowed={'request_too_large','invalid_microphone_input','invalid_text','invalid_expected_speech','notice_text_mismatch','invalid_sound_options','invalid_stream_options','invalid_audio_samples','sound_processing_failed','input_generation_failed','input_too_long','device_mismatch','original_identity_rejected','activation_required','unsupported_audio','audio_packet_gap','audio_packet_size','decode_failed','reply_too_long','reply_incomplete','hello_timeout','recognition_timeout','first_audio_timeout','audio_stalled','service_closed_without_reply','service_error','previous_session_busy'}
        report={'ok':False,'error_type':type(error).__name__,'stage':STAGE}
        report.update(getattr(error,'voice_metrics',{}))
        if isinstance(error,ValueError) and str(error) in allowed:report['error_code']=str(error)
        record(report)
        print(json.dumps(report),file=sys.stderr)
        sys.exit(1)
