from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_json_dumps(payload: dict) -> str:
    return canonical_json_bytes(payload).decode("utf-8")


def sha256_hex_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_hex_canonical_json(payload: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def webauthn_challenge_bytes() -> bytes:
    return secrets.token_bytes(32)


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def b64url_decode(value: str) -> bytes:
    padded = value + "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(padded)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
