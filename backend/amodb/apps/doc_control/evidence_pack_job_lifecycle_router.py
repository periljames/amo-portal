from __future__ import annotations

from fastapi import APIRouter

from .evidence_pack_job_service import start_evidence_pack_job_worker, stop_evidence_pack_job_worker


router = APIRouter()


@router.on_event("startup")
def _start_document_control_evidence_pack_worker() -> None:
    start_evidence_pack_job_worker()


@router.on_event("shutdown")
def _stop_document_control_evidence_pack_worker() -> None:
    stop_evidence_pack_job_worker()
