"""Stable manual revision response and comparison contracts.

These routes precede the core router so Publications receives normalized revision
payloads and a non-error comparison contract.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user, get_current_actor_id
from amodb.apps.accounts import models as account_models

from . import models
from .core_router import _audit, _tenant_by_slug
from .schemas import RevisionCreate, RevisionOut


router = APIRouter(
    prefix="/manuals",
    tags=["Manuals"],
    dependencies=[Depends(get_current_active_user)],
)


def _revision_out(revision: models.ManualRevision) -> RevisionOut:
    return RevisionOut(
        id=revision.id,
        manual_id=revision.manual_id,
        rev_number=revision.rev_number,
        issue_number=revision.issue_number,
        status_enum=str(getattr(revision.status_enum, "value", revision.status_enum)),
        effective_date=revision.effective_date,
        published_at=revision.published_at,
        immutable_locked=bool(revision.immutable_locked),
    )


def _manual_revision(
    db: Session,
    *,
    tenant_id: str,
    manual_id: str,
    revision_id: str,
) -> models.ManualRevision | None:
    return (
        db.query(models.ManualRevision)
        .join(models.Manual, models.Manual.id == models.ManualRevision.manual_id)
        .filter(
            models.Manual.id == manual_id,
            models.Manual.tenant_id == tenant_id,
            models.ManualRevision.id == revision_id,
        )
        .first()
    )


def _revision_text_lines(db: Session, revision_id: str) -> list[str]:
    blocks = (
        db.query(models.ManualBlock)
        .join(models.ManualSection, models.ManualSection.id == models.ManualBlock.section_id)
        .filter(models.ManualSection.revision_id == revision_id)
        .order_by(models.ManualSection.order_index.asc(), models.ManualBlock.order_index.asc())
        .all()
    )
    lines: list[str] = []
    for block in blocks:
        for line in str(block.text_plain or "").splitlines():
            normalized = line.strip()
            if normalized:
                lines.append(normalized)
    return lines


def _line_comparison(
    baseline_lines: list[str],
    current_lines: list[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    baseline: list[dict[str, str]] = []
    current: list[dict[str, str]] = []
    matcher = SequenceMatcher(a=baseline_lines, b=current_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            baseline.extend({"line": line, "kind": "same"} for line in baseline_lines[i1:i2])
            current.extend({"line": line, "kind": "same"} for line in current_lines[j1:j2])
        elif tag == "delete":
            baseline.extend({"line": line, "kind": "removed"} for line in baseline_lines[i1:i2])
        elif tag == "insert":
            current.extend({"line": line, "kind": "added"} for line in current_lines[j1:j2])
        else:
            baseline.extend({"line": line, "kind": "removed"} for line in baseline_lines[i1:i2])
            current.extend({"line": line, "kind": "added"} for line in current_lines[j1:j2])
    return baseline, current


@router.get("/t/{tenant_slug}/{manual_id}/revisions", response_model=list[RevisionOut])
def list_revisions(
    tenant_slug: str,
    manual_id: str,
    db: Session = Depends(get_db),
):
    tenant = _tenant_by_slug(db, tenant_slug)
    manual = (
        db.query(models.Manual)
        .filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id)
        .first()
    )
    if not manual:
        raise HTTPException(status_code=404, detail="Manual not found")
    revisions = (
        db.query(models.ManualRevision)
        .filter(models.ManualRevision.manual_id == manual.id)
        .order_by(models.ManualRevision.created_at.desc(), models.ManualRevision.id.desc())
        .all()
    )
    return [_revision_out(revision) for revision in revisions]


@router.post("/t/{tenant_slug}/{manual_id}/revisions", response_model=RevisionOut)
def create_revision(
    tenant_slug: str,
    manual_id: str,
    payload: RevisionCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant = _tenant_by_slug(db, tenant_slug)
    manual = (
        db.query(models.Manual)
        .filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id)
        .first()
    )
    if not manual:
        raise HTTPException(status_code=404, detail="Manual not found")

    revision = models.ManualRevision(
        manual_id=manual.id,
        rev_number=payload.rev_number,
        issue_number=payload.issue_number,
        effective_date=payload.effective_date,
        notes=payload.notes,
        requires_authority_approval_bool=payload.requires_authority_approval_bool,
        created_by=get_current_actor_id(),
    )
    db.add(revision)
    db.flush()
    _audit(
        db,
        tenant.id,
        get_current_actor_id(),
        "revision.created",
        "manual_revision",
        revision.id,
        request,
        {"rev_number": payload.rev_number},
    )
    db.commit()
    db.refresh(revision)
    return _revision_out(revision)


@router.get("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/compare")
def revision_comparison(
    tenant_slug: str,
    manual_id: str,
    rev_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    # ``current_user`` is intentionally resolved here as well as at router level:
    # it keeps the endpoint contract explicit for dependency/route diagnostics.
    _ = current_user
    tenant = _tenant_by_slug(db, tenant_slug)
    current_revision = _manual_revision(
        db,
        tenant_id=tenant.id,
        manual_id=manual_id,
        revision_id=rev_id,
    )
    if not current_revision:
        raise HTTPException(status_code=404, detail="Revision not found")

    diff = (
        db.query(models.RevisionDiffIndex)
        .filter(models.RevisionDiffIndex.revision_id == current_revision.id)
        .first()
    )
    baseline_id = str(diff.baseline_revision_id) if diff and diff.baseline_revision_id else None
    if not baseline_id:
        return {
            "baseline_revision_id": None,
            "current_lines": [],
            "baseline_lines": [],
        }

    baseline_revision = _manual_revision(
        db,
        tenant_id=tenant.id,
        manual_id=manual_id,
        revision_id=baseline_id,
    )
    if not baseline_revision:
        raise HTTPException(
            status_code=409,
            detail="The recorded comparison baseline is outside this controlled manual.",
        )

    baseline_lines, current_lines = _line_comparison(
        _revision_text_lines(db, baseline_revision.id),
        _revision_text_lines(db, current_revision.id),
    )
    return {
        "baseline_revision_id": baseline_revision.id,
        "current_lines": current_lines,
        "baseline_lines": baseline_lines,
    }
