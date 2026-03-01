from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class ReplicationResult:
    def __init__(self, aws_ok: bool, azure_ok: bool, onprem_ok: bool, errors: Optional[dict[str, str]] = None):
        self.aws_ok = aws_ok
        self.azure_ok = azure_ok
        self.onprem_ok = onprem_ok
        self.errors = errors or {}

    def as_dict(self) -> dict:
        return {
            "aws_ok": self.aws_ok,
            "azure_ok": self.azure_ok,
            "onprem_ok": self.onprem_ok,
            "errors": self.errors,
        }


def _with_retry(fn: Callable[[], bool], retries: int) -> bool:
    for attempt in range(retries + 1):
        if fn():
            return True
        if attempt < retries:
            time.sleep(min(0.2 * (attempt + 1), 1.0))
    return False


def replicate_file(local_path: str, storage_key: str) -> ReplicationResult:
    retries = int(os.getenv("AERODOC_REPLICATION_RETRIES", "2") or "2")
    aws_ok = _with_retry(lambda: _replicate_aws(local_path, storage_key), retries)
    azure_ok = _with_retry(lambda: _replicate_azure(local_path, storage_key), retries)
    onprem_ok = _with_retry(lambda: _replicate_onprem(local_path, storage_key), retries)
    errors: dict[str, str] = {}
    if not aws_ok:
        errors["aws"] = "replication_failed"
    if not azure_ok:
        errors["azure"] = "replication_failed"
    if not onprem_ok:
        errors["onprem"] = "replication_failed"
    return ReplicationResult(aws_ok=aws_ok, azure_ok=azure_ok, onprem_ok=onprem_ok, errors=errors)


def _replicate_aws(local_path: str, storage_key: str) -> bool:
    bucket = os.getenv("AERODOC_AWS_S3_BUCKET", "").strip()
    if bucket:
        try:
            import boto3  # type: ignore

            client = boto3.client("s3")
            client.upload_file(local_path, bucket, storage_key)
            return True
        except Exception as exc:
            logger.warning("AeroDoc AWS S3 replication failed", extra={"error": str(exc), "storage_key": storage_key})
            return False

    bucket_dir = os.getenv("AERODOC_AWS_MIRROR_PATH", "").strip()
    if not bucket_dir:
        return True
    try:
        target = Path(bucket_dir).joinpath(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, target)
        return True
    except Exception as exc:
        logger.warning("AeroDoc AWS mirror replication failed", extra={"error": str(exc), "storage_key": storage_key})
        return False


def _replicate_azure(local_path: str, storage_key: str) -> bool:
    container = os.getenv("AERODOC_AZURE_CONTAINER", "").strip()
    conn_string = os.getenv("AERODOC_AZURE_CONNECTION_STRING", "").strip()
    if container and conn_string:
        try:
            from azure.storage.blob import BlobServiceClient  # type: ignore

            service = BlobServiceClient.from_connection_string(conn_string)
            client = service.get_blob_client(container=container, blob=storage_key)
            with open(local_path, "rb") as data:
                client.upload_blob(data, overwrite=True)
            return True
        except Exception as exc:
            logger.warning("AeroDoc Azure Blob replication failed", extra={"error": str(exc), "storage_key": storage_key})
            return False

    mirror_dir = os.getenv("AERODOC_AZURE_MIRROR_PATH", "").strip()
    if not mirror_dir:
        return True
    try:
        target = Path(mirror_dir).joinpath(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, target)
        return True
    except Exception as exc:
        logger.warning("AeroDoc Azure mirror replication failed", extra={"error": str(exc), "storage_key": storage_key})
        return False


def _replicate_onprem(local_path: str, storage_key: str) -> bool:
    sftp_host = os.getenv("AERODOC_ONPREM_SFTP_HOST", "").strip()
    sftp_user = os.getenv("AERODOC_ONPREM_SFTP_USER", "").strip()
    sftp_pass = os.getenv("AERODOC_ONPREM_SFTP_PASSWORD", "").strip()
    sftp_root = os.getenv("AERODOC_ONPREM_SFTP_ROOT", "").strip() or "/"
    if sftp_host and sftp_user and sftp_pass:
        try:
            import paramiko  # type: ignore

            transport = paramiko.Transport((sftp_host, int(os.getenv("AERODOC_ONPREM_SFTP_PORT", "22") or "22")))
            transport.connect(username=sftp_user, password=sftp_pass)
            sftp = paramiko.SFTPClient.from_transport(transport)
            remote_path = str(Path(sftp_root).joinpath(storage_key)).replace("\\", "/")
            parent = str(Path(remote_path).parent).replace("\\", "/")
            parts = [p for p in parent.split("/") if p]
            cur = ""
            for part in parts:
                cur = f"{cur}/{part}" if cur else f"/{part}"
                try:
                    sftp.stat(cur)
                except Exception:
                    sftp.mkdir(cur)
            sftp.put(local_path, remote_path)
            sftp.close()
            transport.close()
            return True
        except Exception as exc:
            logger.warning("AeroDoc on-prem SFTP replication failed", extra={"error": str(exc), "storage_key": storage_key})
            return False

    onprem_dir = os.getenv("AERODOC_ONPREM_MIRROR_PATH", "").strip()
    if not onprem_dir:
        return True
    try:
        target = Path(onprem_dir).joinpath(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, target)
        return True
    except Exception as exc:
        logger.warning("AeroDoc on-prem mirror replication failed", extra={"error": str(exc), "storage_key": storage_key})
        return False
