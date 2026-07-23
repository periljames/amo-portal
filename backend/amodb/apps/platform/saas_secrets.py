from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from amodb.security import SECRET_KEY


class SecretConfigurationError(RuntimeError):
    pass


def _environment() -> str:
    return (os.getenv("APP_ENV") or os.getenv("ENV") or "development").strip().lower()


def _fernet_key() -> bytes:
    configured = (os.getenv("PLATFORM_SECRETS_KEY") or "").strip()
    if configured:
        try:
            raw = configured.encode("ascii")
            Fernet(raw)
            return raw
        except Exception as exc:
            raise SecretConfigurationError("PLATFORM_SECRETS_KEY must be a valid Fernet key.") from exc

    if _environment() in {"production", "prod"}:
        raise SecretConfigurationError(
            "PLATFORM_SECRETS_KEY is required in production. Generate a Fernet key and store it in the deployment secret manager."
        )

    # Development/test fallback only. It keeps local environments usable while
    # still avoiding plaintext credentials in the database.
    digest = hashlib.sha256(str(SECRET_KEY).encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _cipher() -> Fernet:
    return Fernet(_fernet_key())


def encrypt_secret(payload: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if not payload:
        return None, None
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    encrypted = _cipher().encrypt(canonical).decode("ascii")
    fingerprint = hashlib.sha256(canonical).hexdigest()[:16]
    return encrypted, fingerprint


def decrypt_secret(encrypted: str | None) -> dict[str, Any]:
    if not encrypted:
        return {}
    try:
        raw = _cipher().decrypt(encrypted.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SecretConfigurationError("Stored provider credentials could not be decrypted.") from exc
    if not isinstance(decoded, dict):
        raise SecretConfigurationError("Stored provider credentials have an invalid shape.")
    return decoded


def redact_mapping(value: dict[str, Any] | None) -> dict[str, Any]:
    """Redact likely secrets from diagnostic payloads before persistence/output."""

    secret_markers = {
        "secret",
        "password",
        "token",
        "api_key",
        "apikey",
        "private_key",
        "client_secret",
        "access_key",
        "authorization",
    }

    def clean(item: Any, key: str = "") -> Any:
        lowered = key.lower()
        if any(marker in lowered for marker in secret_markers):
            return "[REDACTED]" if item not in (None, "") else item
        if isinstance(item, dict):
            return {str(k): clean(v, str(k)) for k, v in item.items()}
        if isinstance(item, list):
            return [clean(v, key) for v in item]
        return item

    return clean(value or {})
