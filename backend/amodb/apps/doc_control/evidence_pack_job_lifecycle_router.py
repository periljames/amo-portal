from __future__ import annotations

import os

from fastapi import APIRouter

from .evidence_pack_job_service import start_evidence_pack_job_worker, stop_evidence_pack_job_worker


router = APIRouter()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def embedded_evidence_pack_worker_enabled() -> bool:
    """Return whether the API process should also consume evidence-pack jobs.

    Evidence-pack generation may perform long-running database and filesystem
    work.  Keeping it out of the API process by default prevents background
    packs from exhausting the HTTP connection pool.  Small single-process
    deployments can opt back in explicitly.
    """

    return _env_bool("DOCUMENT_EVIDENCE_PACK_EMBEDDED_WORKER", False)


@router.on_event("startup")
def _start_document_control_evidence_pack_worker() -> None:
    if embedded_evidence_pack_worker_enabled():
        start_evidence_pack_job_worker()


@router.on_event("shutdown")
def _stop_document_control_evidence_pack_worker() -> None:
    if embedded_evidence_pack_worker_enabled():
        stop_evidence_pack_job_worker()
