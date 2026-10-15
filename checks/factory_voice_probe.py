"""受限静音 MQTT 探针：只用本台已有身份，无播放器、麦克风、激活或工具执行。"""
import argparse
import difflib
import json
import os
from pathlib import Path
import select
import socket
import ssl
import struct
import sys
import time

import certifi
from factory_voice_identity import ROOT, read_identity, summary


def mqtt_string(value):
    raw = value.encode('utf-8')
    if len(raw) > 65535:
        raise ValueError('field_too_large')
    return struct.pack('!H', len(raw)) + raw


class Mqtt:
    def __init__(self, config):
        host, separator, port = config['endpoint'].partition(':')
        if host != 'api.tenclass.net' or (separator and int(port) != 8883):
            raise ValueError('unexpected_factory_endpoint')
        self.socket = None
        self.config = config
        self.session = None

    def send(self, header, body=b''):
        length = len(body)
        encoded = bytearray()
        while True:
            digit = length % 128
            length //= 128
            encoded.append(digit | (128 if length else 0))
            if not length:
                break
        self.socket.sendall(bytes([header]) + encoded + body)

    def read_exact(self, size):
        chunks = bytearray()
        while len(chunks) < size:
            data = self.socket.recv(size - len(chunks))
            if not data:
                raise ConnectionError('connection_closed')
            chunks.extend(data)
        return bytes(chunks)

    def packet(self):
        header = self.read_exact(1)[0]
        length = 0
        for index in range(4):
            digit = self.read_exact(1)[0]
            length += (digit & 127) << (7 * index)
            if not digit & 128:
                break
        else:
            raise ValueError('malformed_packet_length')
        if length > 65536:
            raise ValueError('packet_too_large')
        return header, self.read_exact(length)

    def connect(self):
        tls = ssl.create_default_context(cafile=certifi.where())
        raw = socket.create_connection(('api.tenclass.net', 8883), timeout=12)
        try:
            self.socket = tls.wrap_socket(raw, server_hostname='api.tenclass.net')
        except BaseException:
            raw.close()
            raise
        self.socket.settimeout(12)
        config = self.config
        body = mqtt_string('MQTT') + bytes([4, 0xc2]) + struct.pack('!H', 60)
        body += b''.join(mqtt_string(config[key]) for key in ('client_id', 'username', 'password'))
        self.send(0x10, body)
        header, response = self.packet()
        if header != 0x20 or len(response) != 2:
            raise ValueError('invalid_connack')
        return response[1]

    def publish(self, message):
        topic = self.config['publish_topic']
        if not topic or any(character in topic for character in '+#\0'):
            raise ValueError('invalid_publish_topic')
        self.send(0x30, mqtt_string(topic) + json.dumps(message, ensure_ascii=False, separators=(',', ':')).encode())

    def subscribe(self):
        topic = self.config.get('subscribe_topic', '')
        if not topic or topic == 'null':
            return False
        if any(character in topic for character in '+#\0'):
            raise ValueError('wildcard_subscription_forbidden')
        self.send(0x82, struct.pack('!H', 1) + mqtt_string(topic) + b'\0')
        return True

    def message(self):
        header, payload = self.packet()
        if header >> 4 != 3:
            return None
        topic_size = struct.unpack_from('!H', payload)[0]
        offset = 2 + topic_size
        if (header >> 1) & 3:
            packet_id = payload[offset:offset + 2]
            offset += 2
            if ((header >> 1) & 3) == 1:
                self.send(0x40, packet_id)
            else:
                raise ValueError('unsupported_publish_qos')
        return json.loads(payload[offset:])

    def close(self):
        if self.socket is not None:
            try:
                if self.session:
                    self.publish({'type': 'goodbye', 'session_id': self.session})
                self.send(0xe0)
            except (OSError, ValueError):
                pass
            finally:
                self.socket.close()
                self.socket = None


def handle_capabilities(client, message, report):
    if message.get('type') != 'mcp':
        return
    request = message.get('payload')
    if not isinstance(request, dict) or 'id' not in request:
        return
    method = request.get('method')
    response = {'jsonrpc': '2.0', 'id': request['id']}
    if method == 'initialize':
        response['result'] = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}},
                              'serverInfo': {'name': 'weiguang-silent-probe', 'version': '1.0'}}
    elif method == 'tools/list':
        response['result'] = {'tools': []}
    else:
        response['error'] = {'code': -32601, 'message': 'No executable tools in silent probe'}
    report.setdefault('capability_requests', []).append(method if method in ('initialize', 'tools/list', 'tools/call') else 'other')
    client.publish({'session_id': client.session or '', 'type': 'mcp', 'payload': response})


def read_synthetic_opus(path):
    expected = ROOT / '.runtime/fixtures/synthetic-input.ogg'
    if path.resolve() != expected.resolve():
        raise ValueError('only_generated_test_fixture_allowed')
    data = path.read_bytes()
    if len(data) > 100000:
        raise ValueError('test_fixture_too_large')
    offset, pending, packets = 0, bytearray(), []
    while offset < len(data):
        if data[offset:offset + 4] != b'OggS' or data[offset + 4] != 0:
            raise ValueError('invalid_ogg_page')
        count = data[offset + 26]
        lacing = data[offset + 27:offset + 27 + count]
        cursor = offset + 27 + count
        for length in lacing:
            pending.extend(data[cursor:cursor + length]); cursor += length
            if length < 255:
                packets.append(bytes(pending)); pending.clear()
        offset = cursor
    if pending or len(packets) < 3 or not packets[0].startswith(b'OpusHead') or packets[0][9] != 1 or not packets[1].startswith(b'OpusTags'):
        raise ValueError('invalid_mono_opus_fixture')
    audio = packets[2:]
    if not 1 <= len(audio) <= 200:
        raise ValueError('fixture_duration_out_of_bounds')
    return audio


class OrderedAudioPackets:
    """等待乱序；客户端可显式启用有界的Opus丢包补偿。"""
    def __init__(self,sink,report,gap_sink=None):
        self.sink=sink;self.report=report;self.gap_sink=gap_sink;self.pending={};self.expected=None;self.first_at=None;self.gap_at=None;self.highest=-1
    def add(self,sequence,payload,now):
        if sequence in self.pending or (self.expected is not None and sequence<self.expected):
            self.report['duplicate_audio_packets']=self.report.get('duplicate_audio_packets',0)+1;return
        if len(self.pending)>=32:raise ValueError('audio_packet_gap')
        if sequence<self.highest:self.report['reordered_audio_packets']=self.report.get('reordered_audio_packets',0)+1
        self.highest=max(self.highest,sequence)
        if self.first_at is None:self.first_at=now
        self.pending[sequence]=payload
        self.drain(now)
    def drain(self,now,final=False):
        if not self.pending:return
        if self.expected is None:
            if not final and now-self.first_at<0.12:return
            self.expected=min(self.pending)
        while self.pending:
            while self.expected in self.pending:
                self.sink(self.expected,self.pending.pop(self.expected));self.expected+=1;self.gap_at=None
            if not self.pending:return
            if self.gap_at is None:self.gap_at=now
            if not final and now-self.gap_at<0.25:return
            missing=min(self.pending)-self.expected
            self.report['missing_audio_packets']=self.report.get('missing_audio_packets',0)+missing
            if self.gap_sink is None:raise ValueError('audio_packet_gap')
            self.gap_sink(missing)
            self.report['concealed_audio_packets']=self.report.get('concealed_audio_packets',0)+missing
            self.expected+=missing;self.gap_at=None


def send_speech_packets(send_packet,packets,interval,report,guard=0.18):
    # MQTT控制与UDP音频独立传输，给收音开启及尾包留出有界间隔。
    # 这是跨传输时序缓冲，不冒充云端应用层确认。
    time.sleep(guard)
    start=time.monotonic()
    for index,packet in enumerate(packets):
        send_packet(index,packet)
        report['synthetic_speech_packets']=report.get('synthetic_speech_packets',0)+1
        time.sleep(max(0,start+(index+1)*interval-time.monotonic()))
    report['input_upload_seconds']=round(time.monotonic()-start,3)
    time.sleep(guard)
    report['input_guard_ms']=round(guard*1000)


def observe_response(message,report,elapsed):
    kind,state=message.get('type'),message.get('state')
    if kind=='stt':
        report['stt_received']=True
        report.setdefault('stt_seconds',round(elapsed,3))
    if kind=='tts':
        report['tts_started']=report.get('tts_started',False) or state=='start'
        report['tts_stopped']=report.get('tts_stopped',False) or state=='stop'
        if state=='start':report.setdefault('tts_start_seconds',round(elapsed,3))
    if kind=='goodbye' and not report.get('tts_stopped'):
        raise ValueError('service_closed_without_reply')
    if kind=='error':raise ValueError('service_error')


def check_response_wait(report,elapsed,last_audio_elapsed):
    if report.get('tts_stopped'):return
    if report.get('audio_packets',0):
        if last_audio_elapsed is not None and elapsed-last_audio_elapsed>=8:
            raise ValueError('audio_stalled')
    elif report.get('stt_received') or report.get('tts_started'):
        first=report.get('stt_seconds',report.get('tts_start_seconds',0))
        if elapsed-first>=20:raise ValueError('first_audio_timeout')
    elif elapsed>=12:raise ValueError('recognition_timeout')


def text_probe(client, hello, report, order, input_packets=None, packet_sink=None,upload_interval=0.06,tail_wait=2,expected_text=None,gap_sink=None,input_guard=0.18,subtitle_sink=None,transcript_sink=None):
    # 仅安装加密库；没有音频解码器、播放器或录音接口。

    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    udp = hello['udp']
    key, nonce = bytes.fromhex(udp['key']), bytes.fromhex(udp['nonce'])
    if len(key) != 16 or len(nonce) != 16 or nonce[0] != 1:
        raise ValueError('invalid_udp_crypto_parameters')
    if not isinstance(udp['port'], int) or not 1 <= udp['port'] <= 65535:
        raise ValueError('invalid_udp_port')
    report.update(text_requested=input_packets is None, input_order=order, audio_packets=0, audio_bytes=0,
                  tts_started=False, tts_stopped=False, sentence_events=0,
                  expected_reply_observed=False, unexpected_udp_packets=0,
                  voice_id_observed=False, captured_audio_uploaded=False,
                  synthetic_silence_packets=0, synthetic_speech_packets=0, stt_expected_observed=False)
    if input_packets is not None:
        # 正常语音链路先完成能力交换，避免把缺失握手混成输入测试失败。
        capability_start=time.monotonic()
        until = time.monotonic() + 5
        while 'tools/list' not in report.get('capability_requests', []) and time.monotonic() < until:
            readable, _, _ = select.select([client.socket], [], [], 0.25)
            if readable or client.socket.pending():
                message = client.message()
                if isinstance(message, dict):
                    handle_capabilities(client, message, report)
        report['capabilities_before_input'] = 'tools/list' in report.get('capability_requests', [])
        report['capability_wait_seconds']=round(time.monotonic()-capability_start,3)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as audio:
        audio.bind(('0.0.0.0', 0))
        audio.connect((udp['server'], udp['port']))
        # 一帧标准 Opus 静音用于让服务器获知 UDP 回包地址；不来自麦克风。
        silence = b'\xf8\xff\xfe'
        initial = bytearray(nonce)
        struct.pack_into('!H', initial, 2, len(silence))
        struct.pack_into('!I', initial, 8, 0)
        struct.pack_into('!I', initial, 12, 1)
        encryptor = Cipher(algorithms.AES(key), modes.CTR(bytes(initial))).encryptor()
        audio.send(bytes(initial) + encryptor.update(silence) + encryptor.finalize())
        report['synthetic_silence_packets'] = 1
        if order == 'listen-first' or input_packets is not None:
            client.publish({'session_id': client.session, 'type': 'listen', 'state': 'start', 'mode': 'manual'})
        if input_packets is None:
            client.publish({'session_id': client.session, 'type': 'listen', 'state': 'detect',
                            'text': '请只回答：静音验证成功。'})
            report['text_requests_sent'] = 1
        else:
            def send_packet(index,packet):
                header = bytearray(nonce)
                struct.pack_into('!H', header, 2, len(packet))
                struct.pack_into('!I', header, 8, index * 60)
                struct.pack_into('!I', header, 12, index + 2)
                encryptor = Cipher(algorithms.AES(key), modes.CTR(bytes(header))).encryptor()
                audio.send(bytes(header) + encryptor.update(packet) + encryptor.finalize())
            send_speech_packets(send_packet,input_packets,upload_interval,report,input_guard)
            client.publish({'session_id': client.session, 'type': 'listen', 'state': 'stop'})
            report['text_requests_sent'] = 0
        response_start=time.monotonic()
        deadline = response_start + 60
        stopped_at = None
        last_audio_at=None
        report['tail_wait_seconds']=tail_wait
        ordered=OrderedAudioPackets(packet_sink,report,gap_sink=gap_sink) if packet_sink is not None else None
        while time.monotonic() < deadline:
            check_response_wait(report,time.monotonic()-response_start,
                                last_audio_at-response_start if last_audio_at is not None else None)
            if ordered:ordered.drain(time.monotonic())
            if stopped_at and time.monotonic()-max(stopped_at,last_audio_at or stopped_at)>tail_wait:
                if ordered:ordered.drain(time.monotonic(),final=True)
                break
            readable, _, _ = select.select([client.socket, audio], [], [], 0.25)
            if client.socket.pending() or client.socket in readable:
                message = client.message()
                if isinstance(message, dict):
                    handle_capabilities(client, message, report)
                    kind, state = message.get('type'), message.get('state')
                    report['events'].append({'type': kind if kind in ('hello', 'goodbye', 'tts', 'stt', 'llm', 'mcp', 'error') else 'other',
                                             'state': state if state in ('start', 'stop', 'sentence_start', 'sentence_end') else None})
                    observe_response(message,report,time.monotonic()-response_start)
                    if kind == 'tts':
                        report['tts_started'] |= state == 'start'
                        report['tts_stopped'] |= state == 'stop'
                        if state == 'stop':
                            stopped_at = time.monotonic()
                        if state == 'sentence_start':
                            report['sentence_events'] += 1
                            report['expected_reply_observed'] |= '静音验证成功' in str(message.get('text', ''))
                            if subtitle_sink is not None:subtitle_sink(message.get('text'))
                        report['voice_id_observed'] |= bool(message.get('voice_id') or message.get('tts_voice'))
                    if kind == 'stt':
                        if transcript_sink is not None:transcript_sink(message.get('text'))
                        report['stt_received']=True
                        report['stt_expected_observed'] |= '静音验证成功' in str(message.get('text', ''))
                        if expected_text:
                            normalize=lambda text:''.join(c for c in text if c.isalnum())
                            ratio=difflib.SequenceMatcher(None,normalize(expected_text),normalize(str(message.get('text','')))).ratio()
                            report['stt_input_similarity']=round(ratio,3)
                            report['stt_input_matched']=ratio>=0.85
                            report['stt_character_count']=len(normalize(str(message.get('text',''))))
                    if kind in ('activation', 'activate') or 'activation' in message:
                        raise ValueError('activation_required_stopped')
                    # 不响应云端工具执行、系统控制或自定义设备指令。
            if audio in readable:
                packet = audio.recv(8192)
                if len(packet) < 17 or packet[0] != 1 or struct.unpack_from('!H', packet, 2)[0] != len(packet) - 16:
                    report['unexpected_udp_packets'] += 1
                    continue
                decryptor = Cipher(algorithms.AES(key), modes.CTR(packet[:16])).decryptor()
                payload = decryptor.update(packet[16:]) + decryptor.finalize()
                report['audio_packets'] += 1
                report['audio_bytes'] += len(payload)
                last_audio_at=time.monotonic()
                # 静音探针默认丢弃；独立耳机客户端可显式接收，CLI不提供该选项。
                if ordered is not None:
                    ordered.add(struct.unpack_from('!I',packet,12)[0],payload,time.monotonic())
                del payload
    report['text_audio_passed'] = report['expected_reply_observed'] and report['tts_stopped'] and report['audio_packets'] > 0
    report['result'] = 'silent_text_audio_received' if report['text_audio_passed'] else 'text_audio_not_confirmed'
    if input_packets is not None:
        report['speech_audio_passed'] = report['stt_expected_observed'] and report['tts_stopped'] and report['audio_packets'] > 0
        report['result'] = 'silent_speech_audio_received' if report['speech_audio_passed'] else 'speech_audio_not_confirmed'


def probe(with_text=False, order='listen-first', audio_file=None):
    report = {'mode': 'cached-original-device-mqtt-handshake', 'audio_output_created': False,
              'microphone_opened': False, 'device_commands_sent': False,
              'activation_attempted': False, 'role_modified': False, 'secrets_saved': False,
              'ok': False, 'events': []}
    client = None
    try:
        input_packets = read_synthetic_opus(audio_file) if audio_file else None
        identity = read_identity()
        report['identity'] = summary(identity)
        if not report['identity']['bound_device_matches_mqtt_client']:
            raise ValueError('device_identity_mismatch')
        client = Mqtt(identity['mqtt'])
        code = client.connect()
        report['mqtt_connack_code'] = code
        report['tls_verified'] = True
        if code != 0:
            report['result'] = 'cached_credentials_rejected'
            return report
        report['mqtt_authenticated'] = True
        report['explicit_subscription'] = client.subscribe()
        client.publish({'type': 'hello', 'version': 3, 'transport': 'udp', 'features': {'mcp': False},
                        'audio_params': {'format': 'opus', 'sample_rate': 16000, 'channels': 1, 'frame_duration': 60}})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            message = client.message()
            if not isinstance(message, dict):
                continue
            kind = message.get('type')
            handle_capabilities(client, message, report)
            if kind in ('activation', 'activate') or any(key in message for key in ('activation', 'activation_code')):
                report['result'] = 'activation_required_stopped'
                break
            report['events'].append({'type': kind if kind in ('hello', 'goodbye', 'tts', 'stt', 'llm', 'mcp', 'error') else 'other'})
            if kind == 'hello':
                client.session = message.get('session_id')
                report['session_received'] = bool(client.session)
                report['transport'] = message.get('transport')
                audio = message.get('audio_params') or {}
                report['audio_params'] = {key: audio.get(key) for key in ('format', 'sample_rate', 'channels', 'frame_duration')}
                udp = message.get('udp') or {}
                report['udp_config_complete'] = all(udp.get(key) is not None for key in ('server', 'port', 'key', 'nonce'))
                report['ok'] = bool(client.session) and report['udp_config_complete']
                report['result'] = 'original_cached_session_accepted' if report['ok'] else 'incomplete_server_hello'
                if report['ok'] and (with_text or input_packets is not None):
                    text_probe(client, message, report, order, input_packets)
                    report['ok'] = report.get('speech_audio_passed' if input_packets is not None else 'text_audio_passed', False)
                break
        else:
            report['result'] = 'server_hello_timeout'
    except Exception as error:
        report['ok'] = False
        report['result'] = 'probe_failed'
        report['error_type'] = type(error).__name__
        if isinstance(error, OSError):
            report['error_number'] = error.errno
    finally:
        if client:
            client.close()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument('--text', action='store_true')
    input_group.add_argument('--audio-file', type=Path)
    parser.add_argument('--order', choices=('listen-first', 'detect-only'), default='listen-first')
    args = parser.parse_args()
    result = probe(args.text, args.order, args.audio_file)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(text)
    print(text)
