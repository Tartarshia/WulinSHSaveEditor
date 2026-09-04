"""Local reader/writer for WulinSH Easy Save 3 files."""
from __future__ import annotations

import gzip
import json
import os
import re
import tempfile
from dataclasses import dataclass
from hashlib import pbkdf2_hmac
from pathlib import Path
from typing import Any

from Crypto.Cipher import AES

PASSWORD = b"Meow"
_NUMERIC_KEYS = re.compile(r'([,{])"(-?\d+)":')
_UNQUOTED_NUMERIC_KEYS = re.compile(r'([,{])(-?\d+):')


class SaveFormatError(ValueError):
    pass


def _decrypt(encrypted: bytes) -> bytes:
    if len(encrypted) < 32 or len(encrypted) % 16:
        raise SaveFormatError("不是有效的 ES3 AES 文件长度")
    iv = encrypted[:16]
    key = pbkdf2_hmac("sha1", PASSWORD, iv, 100, dklen=16)
    padded = AES.new(key, AES.MODE_CBC, iv).decrypt(encrypted[16:])
    pad = padded[-1]
    if not 1 <= pad <= 16 or padded[-pad:] != bytes([pad]) * pad:
        raise SaveFormatError("ES3 密码或填充校验失败")
    return padded[:-pad]


def _encrypt(payload: bytes) -> bytes:
    iv = os.urandom(16)
    key = pbkdf2_hmac("sha1", PASSWORD, iv, 100, dklen=16)
    pad = 16 - len(payload) % 16
    return iv + AES.new(key, AES.MODE_CBC, iv).encrypt(payload + bytes([pad]) * pad)


def _parse_es3_json(clear: bytes) -> Any:
    try:
        text = clear.decode("utf-8")
        # ES3 emits dictionary keys which are integer IDs without JSON quotes.
        return json.loads(_UNQUOTED_NUMERIC_KEYS.sub(r'\1"\2":', text))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SaveFormatError(f"ES3 JSON 解析失败：{exc}") from exc


def _dump_es3_json(data: Any) -> bytes:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return _NUMERIC_KEYS.sub(r"\1\2:", text).encode("utf-8")


def load(path: Path) -> Any:
    try:
        return _parse_es3_json(gzip.decompress(_decrypt(path.read_bytes())))
    except OSError as exc:
        raise SaveFormatError(f"GZip 解压失败：{exc}") from exc


def encode(data: Any) -> bytes:
    return _encrypt(gzip.compress(_dump_es3_json(data), mtime=0))


def atomic_write(path: Path, data: Any) -> None:
    payload = encode(data)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as tmp:
        tmp.write(payload)
        temp_path = Path(tmp.name)
    try:
        # Decode the bytes which will be written before replacing the real save.
        if _parse_es3_json(gzip.decompress(_decrypt(temp_path.read_bytes()))) != data:
            raise SaveFormatError("写后回读校验失败")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
