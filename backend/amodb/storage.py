from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlparse
from uuid import uuid4

logger = logging.getLogger(__name__)

_SAFE_KEY = re.compile(r"[^A-Za-z0-9._/\-]+")
_CLIENT_LOCK = threading.Lock()
_CLIENT = None
_CACHE_CLEANUP_LOCK = threading.Lock()
_LAST_CACHE_CLEANUP = 0.0


def _bool(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "")).strip().lower()
    return default if not value else value in {"1", "true", "yes", "on"}


def _backend() -> str:
    value = str(os.getenv("AMO_STORAGE_BACKEND", "local") or "local").strip().lower()
    if value not in {"local", "s3"}:
        raise RuntimeError("AMO_STORAGE_BACKEND must be 'local' or 's3'")
    return value


def local_root() -> Path:
    return Path(os.getenv("AMO_STORAGE_LOCAL_ROOT", "/srv/amo/uploads")).resolve()


def cache_root() -> Path:
    return Path(os.getenv("AMO_STORAGE_CACHE_DIR", "/tmp/amo-object-cache")).resolve()


def bucket_name() -> str:
    return str(os.getenv("AMO_STORAGE_S3_BUCKET", "") or "").strip()


def object_prefix() -> str:
    return str(os.getenv("AMO_STORAGE_S3_PREFIX", "amo-portal") or "amo-portal").strip(" /")


def shared_storage_enabled() -> bool:
    return _backend() == "s3"


def validate_storage_configuration(*, require_shared: bool | None = None) -> dict[str, str | bool]:
    backend = _backend()
    required = _bool("AMO_REQUIRE_SHARED_STORAGE", False) if require_shared is None else require_shared
    if required and backend != "s3":
        raise RuntimeError("Horizontal application mode requires AMO_STORAGE_BACKEND=s3")
    if backend == "s3" and not bucket_name():
        raise RuntimeError("AMO_STORAGE_S3_BUCKET is required when AMO_STORAGE_BACKEND=s3")
    root = local_root()
    if backend == "local":
        root.mkdir(parents=True, exist_ok=True)
    return {"backend": backend, "shared": backend == "s3", "bucket_configured": bool(bucket_name()), "require_shared": required}


def normalise_key(value: str) -> str:
    cleaned = _SAFE_KEY.sub("_", str(value or "").replace("\\", "/")).strip(" /")
    parts = [part for part in cleaned.split("/") if part not in {"", ".", ".."}]
    if not parts:
        raise ValueError("Object storage key is empty")
    return "/".join(parts)[:1024]


def _full_key(key: str) -> str:
    clean = normalise_key(key)
    prefix = object_prefix()
    return f"{prefix}/{clean}" if prefix else clean


def _client():
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is not None:
            return _CLIENT
        import boto3
        from botocore.config import Config

        kwargs: dict = {
            "config": Config(
                connect_timeout=max(1, int(os.getenv("AMO_STORAGE_CONNECT_TIMEOUT_SEC", "3") or "3")),
                read_timeout=max(1, int(os.getenv("AMO_STORAGE_READ_TIMEOUT_SEC", "30") or "30")),
                retries={"max_attempts": max(1, int(os.getenv("AMO_STORAGE_MAX_ATTEMPTS", "3") or "3")), "mode": "standard"},
                s3={"addressing_style": str(os.getenv("AMO_STORAGE_S3_ADDRESSING_STYLE", "auto") or "auto")},
            )
        }
        endpoint = str(os.getenv("AMO_STORAGE_S3_ENDPOINT_URL", "") or "").strip()
        region = str(os.getenv("AMO_STORAGE_S3_REGION", "") or "").strip()
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        if region:
            kwargs["region_name"] = region
        _CLIENT = boto3.client("s3", **kwargs)
        return _CLIENT


def _extra_args(content_type: str | None = None) -> dict:
    args: dict[str, str] = {}
    if content_type:
        args["ContentType"] = content_type
    sse = str(os.getenv("AMO_STORAGE_S3_SSE", "") or "").strip()
    kms = str(os.getenv("AMO_STORAGE_S3_KMS_KEY_ID", "") or "").strip()
    if sse:
        args["ServerSideEncryption"] = sse
    if kms:
        args["SSEKMSKeyId"] = kms
    return args


def _cache_limits() -> tuple[int, int]:
    max_bytes = max(64 * 1024 * 1024, int(os.getenv("AMO_STORAGE_CACHE_MAX_BYTES", str(2 * 1024 * 1024 * 1024)) or str(2 * 1024 * 1024 * 1024)))
    max_age = max(300, int(os.getenv("AMO_STORAGE_CACHE_MAX_AGE_SEC", str(24 * 3600)) or str(24 * 3600)))
    return max_bytes, max_age


def cleanup_cache(*, force: bool = False) -> None:
    global _LAST_CACHE_CLEANUP
    root = cache_root()
    if not root.exists():
        return
    now_mono = time.monotonic()
    with _CACHE_CLEANUP_LOCK:
        if not force and now_mono - _LAST_CACHE_CLEANUP < 60:
            return
        _LAST_CACHE_CLEANUP = now_mono
        max_bytes, max_age = _cache_limits()
        now = time.time()
        files: list[tuple[float, int, Path]] = []
        total = 0
        for path in root.iterdir():
            if not path.is_file() or path.name.startswith("amo-upload-") or path.name.endswith(".downloading"):
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            if now - stat.st_mtime > max_age:
                path.unlink(missing_ok=True)
                continue
            total += stat.st_size
            files.append((stat.st_mtime, stat.st_size, path))
        if total <= max_bytes:
            return
        for _mtime, size, path in sorted(files):
            path.unlink(missing_ok=True)
            total -= size
            if total <= max_bytes:
                break


@dataclass(frozen=True)
class StoredObject:
    uri: str
    key: str
    backend: str
    size_bytes: int | None = None
    etag: str | None = None


def put_file(path: str | Path, *, key: str, content_type: str | None = None) -> StoredObject:
    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(str(source))
    backend = _backend()
    clean = normalise_key(key)
    if backend == "local":
        root = local_root()
        root.mkdir(parents=True, exist_ok=True)
        target = (root / clean).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("Storage key escapes configured local root") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.uploading")
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
        return StoredObject(uri=str(target), key=clean, backend="local", size_bytes=target.stat().st_size)

    validate_storage_configuration()
    full_key = _full_key(clean)
    args = _extra_args(content_type)
    if args:
        _client().upload_file(str(source), bucket_name(), full_key, ExtraArgs=args)
    else:
        _client().upload_file(str(source), bucket_name(), full_key)
    head = _client().head_object(Bucket=bucket_name(), Key=full_key)
    return StoredObject(
        uri=f"s3://{bucket_name()}/{full_key}",
        key=clean,
        backend="s3",
        size_bytes=int(head.get("ContentLength") or source.stat().st_size),
        etag=str(head.get("ETag") or "").strip('"') or None,
    )


def put_stream(stream: BinaryIO, *, key: str, content_type: str | None = None) -> StoredObject:
    root = cache_root()
    root.mkdir(parents=True, exist_ok=True)
    cleanup_cache()
    fd, raw_path = tempfile.mkstemp(prefix="amo-upload-", dir=str(root))
    os.close(fd)
    path = Path(raw_path)
    try:
        with path.open("wb") as handle:
            shutil.copyfileobj(stream, handle, length=1024 * 1024)
        return put_file(path, key=key, content_type=content_type)
    finally:
        path.unlink(missing_ok=True)


def _parse_s3(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError("Invalid S3 object URI")
    return parsed.netloc, parsed.path.lstrip("/")


def materialize(uri: str, *, expected_sha256: str | None = None) -> Path:
    if not str(uri or "").startswith("s3://"):
        path = Path(uri).resolve()
        root = local_root()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("Local object path is outside configured storage root") from exc
        if not path.is_file():
            raise FileNotFoundError(str(path))
        return path

    bucket, key = _parse_s3(uri)
    root = cache_root()
    root.mkdir(parents=True, exist_ok=True)
    cleanup_cache()
    suffix = Path(key).suffix[:16]
    digest = hashlib.sha256(uri.encode()).hexdigest()
    target = root / f"{digest}{suffix}"
    if target.is_file():
        if not expected_sha256 or _sha256(target) == expected_sha256:
            try:
                os.utime(target, None)
            except OSError:
                pass
            return target
        target.unlink(missing_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.downloading")
    try:
        _client().download_file(bucket, key, str(temporary))
        if expected_sha256 and _sha256(temporary) != expected_sha256:
            raise IOError("Object checksum verification failed")
        os.replace(temporary, target)
        cleanup_cache(force=True)
        return target
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def delete(uri: str) -> None:
    if not uri:
        return
    if uri.startswith("s3://"):
        bucket, key = _parse_s3(uri)
        _client().delete_object(Bucket=bucket, Key=key)
        cached = cache_root() / f"{hashlib.sha256(uri.encode()).hexdigest()}{Path(key).suffix[:16]}"
        cached.unlink(missing_ok=True)
        return
    path = Path(uri).resolve()
    root = local_root()
    try:
        path.relative_to(root)
    except ValueError:
        return
    path.unlink(missing_ok=True)


def exists(uri: str) -> bool:
    if not uri:
        return False
    if uri.startswith("s3://"):
        try:
            bucket, key = _parse_s3(uri)
            _client().head_object(Bucket=bucket, Key=key)
            return True
        except Exception:
            return False
    try:
        path = Path(uri).resolve()
        path.relative_to(local_root())
        return path.is_file()
    except Exception:
        return False


def health_check() -> dict[str, object]:
    config = validate_storage_configuration()
    probe_name = f".amo-storage-probe-{os.getpid()}-{uuid4().hex}"
    if _backend() == "local":
        root = local_root()
        probe = root / probe_name
        try:
            probe.write_bytes(b"ok")
            ok = probe.read_bytes() == b"ok"
            return {**config, "ok": ok, "detail": str(root)}
        finally:
            probe.unlink(missing_ok=True)
    key = _full_key(f"health/{probe_name}.txt")
    try:
        _client().put_object(Bucket=bucket_name(), Key=key, Body=b"ok", **_extra_args("text/plain"))
        body = _client().get_object(Bucket=bucket_name(), Key=key)["Body"].read(2)
        return {**config, "ok": body == b"ok", "detail": f"s3://{bucket_name()}/{object_prefix()}"}
    finally:
        try:
            _client().delete_object(Bucket=bucket_name(), Key=key)
        except Exception:
            logger.debug("Unable to delete storage health probe", exc_info=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
