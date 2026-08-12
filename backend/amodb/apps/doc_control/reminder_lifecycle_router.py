from __future__ import annotations

from fastapi import APIRouter

from .reminder_service import (
    start_document_control_reminder_scheduler,
    stop_document_control_reminder_scheduler,
)


router = APIRouter()


@router.on_event("startup")
def _start_document_control_reminders() -> None:
    start_document_control_reminder_scheduler()


@router.on_event("shutdown")
def _stop_document_control_reminders() -> None:
    stop_document_control_reminder_scheduler()
