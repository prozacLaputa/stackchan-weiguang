"""原厂备份的连接字段只读解析；秘密值仅留内存，默认只输出存在性与目标主机。"""
import hashlib
import json
from pathlib import Path
import re
import struct
from urllib.parse import urlsplit
import zlib

ROOT = Path(__file__).resolve().parent.parent

FIELDS = {
    'board': {'uuid'},
    'wifi': {'ota_url'},
    'mqtt': {'endpoint', 'client_id', 'username', 'password', 'publish_topic', 'subscribe_topic', 'keepalive'},
    'websocket': {'url', 'token', 'version'},
}


def crc(data):
    return zlib.crc32(data, 0xffffffff) & 0xffffffff


def read_identity():
    data = (ROOT / 'backups/factory.bin').read_bytes()
    fields = (ROOT / 'backups/factory.sha256').read_text().split()
    checksum = fields[0].lower() if fields else ''
    if not re.fullmatch(r'[0-9a-f]{64}', checksum) or hashlib.sha256(data).hexdigest() != checksum:
        raise ValueError('factory_backup_checksum_mismatch')
    nvs = None
    for offset in range(0x8000, 0x8c00, 32):
        entry = data[offset:offset + 32]
        if entry[:2] != b'\xaa\x50':
            break
        _, kind, sub, start, size, label, flags = struct.unpack('<HBBII16sI', entry)
        if label.split(b'\0')[0] == b'nvs' and (kind, sub) == (1, 2):
            if flags or size % 4096 or start + size > len(data):
                raise ValueError('unsupported_nvs_partition')
            nvs = data[start:start + size]
    if nvs is None:
        raise ValueError('nvs_not_found')
    entries = []
    for offset in range(0, len(nvs), 4096):
        page = nvs[offset:offset + 4096]
        if page[:4] == b'\xff' * 4:
            continue
        state, sequence = struct.unpack_from('<II', page)
        if state not in (0xfffffffe, 0xfffffffc) or crc(page[4:28]) != struct.unpack_from('<I', page, 28)[0]:
            raise ValueError('invalid_nvs_page')
        bitmap = int.from_bytes(page[32:64], 'little')
        index = 0
        while index < 126:
            if (bitmap >> (index * 2)) & 3 != 2:
                index += 1
                continue
            entry = page[64 + index * 32:96 + index * 32]
            namespace, kind, span, _ = entry[:4]
            if span < 1 or index + span > 126 or crc(entry[:4] + entry[8:]) != struct.unpack_from('<I', entry, 4)[0]:
                raise ValueError('invalid_nvs_entry')
            key = entry[8:24].split(b'\0')[0].decode('ascii')
            # 不解码其他命名空间的值，包括 Wi-Fi 账号、密码和 App 账号。
            entries.append((sequence, index, namespace, kind, key, entry, page))
            index += span
    entries.sort(key=lambda item: item[:2])
    namespaces = {item[5][24]: item[4] for item in entries if item[2:4] == (0, 1)}
    result = {name: {} for name in FIELDS}
    for _, index, namespace, kind, key, entry, page in entries:
        name = namespaces.get(namespace)
        if name not in FIELDS or key not in FIELDS[name]:
            continue
        if kind == 0x21:
            size = struct.unpack_from('<H', entry, 24)[0]
            if size < 1 or size > (entry[2] - 1) * 32:
                raise ValueError('invalid_nvs_string_size')
            value = page[96 + index * 32:96 + index * 32 + size]
            if crc(value) != struct.unpack_from('<I', entry, 28)[0] or value[-1] != 0:
                raise ValueError('invalid_nvs_string')
            result[name][key] = value[:-1].decode('utf-8')
        elif kind in (1, 2, 4, 8, 0x11, 0x12, 0x14, 0x18):
            size = kind & 15
            result[name][key] = int.from_bytes(entry[24:24 + size], 'little', signed=bool(kind & 0x10))
        else:
            raise ValueError('unsupported_connection_value_type')
    config = json.loads((Path.home() / 'Library/Application Support/Weiguang/config.json').read_text())
    mac = config.get('serial_number', '').lower().replace('-', ':')
    if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', mac):
        raise ValueError('bound_device_id_unavailable')
    result['device_id'] = mac
    return result


def summary(identity):
    mqtt = identity['mqtt']
    websocket = identity['websocket']
    address = mqtt.get('endpoint', '')
    ws = urlsplit(websocket.get('url', ''))
    identifier = re.sub('[^0-9a-f]', '', identity['device_id'])
    client = mqtt.get('client_id', '').lower()
    matched = identity['device_id'] in client or identifier in client.replace('_', '').replace(':', '').replace('-', '')
    return {
        'backup_checksum_verified': True,
        'nvs_crc_verified': True,
        'bound_device_matches_mqtt_client': matched,
        'board_uuid_present': bool(identity['board'].get('uuid')),
        'mqtt_fields_present': {key: bool(mqtt.get(key)) for key in sorted(FIELDS['mqtt'])},
        'mqtt_host': address.split(':')[0],
        'mqtt_port': int(address.split(':')[1]) if ':' in address else 8883,
        'websocket_host': ws.hostname,
        'websocket_secure': ws.scheme == 'wss',
        'websocket_token_present': bool(websocket.get('token')),
        'websocket_token_is_placeholder': websocket.get('token') in ('', 'test-token'),
        'ota_override_present': bool(identity['wifi'].get('ota_url')),
    }


if __name__ == '__main__':
    try:
        print(json.dumps(summary(read_identity()), ensure_ascii=False, indent=2))
    except Exception as error:
        # 不打印异常值或 traceback，防止网络／配置对象泄露身份。
        print(json.dumps({'ok': False, 'error_type': type(error).__name__}))
        raise SystemExit(1)
