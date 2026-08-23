from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import knowledge_models as km
from .workspace_service import require_control_user, resolve_tenant, utcnow


router = APIRouter(prefix="/workspace", tags=["Document Control Evidence Registers"])

REPORT_VIEWS = {
    "revisions",
    "lep",
    "distribution",
    "acknowledgements",
    "controlled-copies",
    "external-sources",
    "review-due",
    "temporary-revisions",
    "authority",
    "archive",
    "change-history",
    "retention",
}


def _date_bounds(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(date_from, time.min) if date_from else None
    end = datetime.combine(date_to, time.max) if date_to else None
    return start, end


def _manual_search_conditions(needle: str):
    return (
        manual_models.Manual.code.ilike(needle),
        manual_models.Manual.title.ilike(needle),
        manual_models.Manual.manual_type.ilike(needle),
    )


def _apply_manual_search(query, q: str | None):
    if not q or not q.strip():
        return query
    needle = f"%{q.strip()}%"
    return query.filter(or_(*_manual_search_conditions(needle)))


def _manual_payload(manual: manual_models.Manual) -> dict[str, str]:
    return {"id": manual.id, "code": manual.code, "title": manual.title, "type": manual.manual_type}


def _item(
    *,
    record_id: str,
    kind: str,
    manual: manual_models.Manual,
    record: str,
    status: str | None,
    owner: str | None = None,
    date_value: datetime | date | None = None,
    due_value: datetime | date | None = None,
    context: str | None = None,
    target_path: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": record_id,
        "kind": kind,
        "document": _manual_payload(manual),
        "record": record,
        "status": status,
        "owner": owner,
        "date": date_value.isoformat() if date_value else None,
        "due_at": due_value.isoformat() if due_value else None,
        "context": context,
        "target_path": target_path or f"library/{manual.id}",
        "details": details or {},
    }


def _paginate(query, page: int, per_page: int):
    total = int(query.order_by(None).count())
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    return total, rows


@router.get("/t/{tenant_slug}/reports-register")
def get_reports_register(
    tenant_slug: str,
    view: str = Query(default="revisions", pattern="^(revisions|lep|distribution|acknowledgements|controlled-copies|external-sources|review-due|temporary-revisions|authority|archive|change-history|retention)$"),
    q: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None, max_length=48),
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return one bounded authoritative DMS evidence register.

    The canonical Reports workspace selects a report family here instead of
    loading complete domain tables into the browser. Each result retains its
    source entity identity and links to the operational owner of the evidence.
    """
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    start, end = _date_bounds(date_from, date_to)
    wanted_status = status.strip().upper() if status else None
    items: list[dict[str, Any]] = []

    if view == "revisions":
        query = (
            db.query(manual_models.ManualRevision, manual_models.Manual)
            .join(manual_models.Manual, manual_models.Manual.id == manual_models.ManualRevision.manual_id)
            .filter(manual_models.Manual.tenant_id == tenant.id)
        )
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(or_(
                *_manual_search_conditions(needle),
                manual_models.ManualRevision.rev_number.ilike(needle),
                manual_models.ManualRevision.issue_number.ilike(needle),
                manual_models.ManualRevision.source_filename.ilike(needle),
            ))
        if wanted_status:
            revision_status = manual_models.ManualRevisionStatus.__members__.get(wanted_status)
            query = query.filter(manual_models.ManualRevision.status_enum == revision_status) if revision_status else query.filter(False)
        if start:
            query = query.filter(manual_models.ManualRevision.created_at >= start)
        if end:
            query = query.filter(manual_models.ManualRevision.created_at <= end)
        query = query.order_by(manual_models.ManualRevision.created_at.desc(), manual_models.ManualRevision.id.desc())
        total, rows = _paginate(query, page, per_page)
        for revision, manual in rows:
            raw_status = str(getattr(revision.status_enum, "value", revision.status_enum or ""))
            label = f"{('Issue ' + revision.issue_number + ' · ') if revision.issue_number else ''}Rev {revision.rev_number}"
            items.append(_item(
                record_id=revision.id,
                kind="REVISION",
                manual=manual,
                record=label,
                status=raw_status,
                date_value=revision.effective_date or revision.created_at,
                context=revision.source_filename or "Controlled revision",
                target_path=f"library/{manual.id}?tab=content",
                details={"source_filename": revision.source_filename, "page_count": revision.source_page_count},
            ))

    elif view == "lep":
        query = (
            db.query(manual_models.Manual, manual_models.ManualRevision)
            .join(manual_models.ManualRevision, manual_models.ManualRevision.id == manual_models.Manual.current_published_rev_id)
            .filter(manual_models.Manual.tenant_id == tenant.id)
        )
        query = _apply_manual_search(query, q).order_by(manual_models.Manual.code.asc())
        total, rows = _paginate(query, page, per_page)
        for manual, revision in rows:
            items.append(_item(
                record_id=revision.id,
                kind="LEP",
                manual=manual,
                record="List of Effective Pages",
                status="CURRENT",
                date_value=revision.effective_date,
                context=f"{revision.source_page_count or 0} source page(s) · Rev {revision.rev_number}",
                target_path=f"library/{manual.id}?tab=changes&view=lep",
                details={"page_count": revision.source_page_count, "revision_number": revision.rev_number, "issue_number": revision.issue_number},
            ))

    elif view == "distribution":
        query = (
            db.query(dm.DocumentDistributionCampaign, manual_models.Manual)
            .join(manual_models.Manual, manual_models.Manual.id == dm.DocumentDistributionCampaign.manual_id)
            .filter(dm.DocumentDistributionCampaign.tenant_id == tenant.amo_id)
        )
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(or_(*_manual_search_conditions(needle), dm.DocumentDistributionCampaign.title.ilike(needle)))
        if wanted_status:
            query = query.filter(dm.DocumentDistributionCampaign.status == wanted_status)
        if start:
            query = query.filter(dm.DocumentDistributionCampaign.created_at >= start)
        if end:
            query = query.filter(dm.DocumentDistributionCampaign.created_at <= end)
        query = query.order_by(dm.DocumentDistributionCampaign.created_at.desc())
        total, rows = _paginate(query, page, per_page)
        for campaign, manual in rows:
            items.append(_item(
                record_id=campaign.id,
                kind="DISTRIBUTION",
                manual=manual,
                record=campaign.title,
                status=campaign.status,
                date_value=campaign.issued_at or campaign.created_at,
                due_value=campaign.due_at,
                context="Acknowledgement required" if campaign.acknowledgement_required else "No acknowledgement required",
                target_path=f"library/{manual.id}?tab=distribution&campaign={campaign.id}",
            ))

    elif view == "acknowledgements":
        query = (
            db.query(dm.DocumentDistributionRecipient, dm.DocumentDistributionCampaign, manual_models.Manual, account_models.User)
            .join(dm.DocumentDistributionCampaign, dm.DocumentDistributionCampaign.id == dm.DocumentDistributionRecipient.campaign_id)
            .join(manual_models.Manual, manual_models.Manual.id == dm.DocumentDistributionCampaign.manual_id)
            .outerjoin(account_models.User, account_models.User.id == dm.DocumentDistributionRecipient.recipient_user_id)
            .filter(dm.DocumentDistributionRecipient.tenant_id == tenant.amo_id)
        )
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(or_(
                *_manual_search_conditions(needle),
                dm.DocumentDistributionCampaign.title.ilike(needle),
                account_models.User.full_name.ilike(needle),
                account_models.User.email.ilike(needle),
            ))
        if wanted_status:
            query = query.filter(dm.DocumentDistributionRecipient.status == wanted_status)
        if start:
            query = query.filter(dm.DocumentDistributionRecipient.due_at >= start)
        if end:
            query = query.filter(dm.DocumentDistributionRecipient.due_at <= end)
        query = query.order_by(dm.DocumentDistributionRecipient.due_at.asc().nullslast(), dm.DocumentDistributionRecipient.id.asc())
        total, rows = _paginate(query, page, per_page)
        for recipient, campaign, manual, user in rows:
            items.append(_item(
                record_id=recipient.id,
                kind="ACKNOWLEDGEMENT",
                manual=manual,
                record=campaign.title,
                status=recipient.status,
                owner=(user.full_name if user else None) or "Unassigned recipient",
                date_value=recipient.acknowledged_at or recipient.notified_at,
                due_value=recipient.due_at,
                context=f"Reminders: {recipient.reminder_count}",
                target_path=f"library/{manual.id}?tab=distribution&campaign={campaign.id}",
            ))

    elif view == "controlled-copies":
        query = (
            db.query(dm.DocumentControlledCopy, manual_models.Manual)
            .join(manual_models.Manual, manual_models.Manual.id == dm.DocumentControlledCopy.manual_id)
            .filter(dm.DocumentControlledCopy.tenant_id == tenant.amo_id)
        )
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(or_(
                *_manual_search_conditions(needle),
                dm.DocumentControlledCopy.copy_number.ilike(needle),
                dm.DocumentControlledCopy.holder_name.ilike(needle),
                dm.DocumentControlledCopy.location_text.ilike(needle),
            ))
        if wanted_status:
            query = query.filter(dm.DocumentControlledCopy.status == wanted_status)
        if start:
            query = query.filter(dm.DocumentControlledCopy.issued_at >= start)
        if end:
            query = query.filter(dm.DocumentControlledCopy.issued_at <= end)
        query = query.order_by(dm.DocumentControlledCopy.issued_at.desc())
        total, rows = _paginate(query, page, per_page)
        for copy, manual in rows:
            items.append(_item(
                record_id=copy.id,
                kind="CONTROLLED_COPY",
                manual=manual,
                record=f"Copy {copy.copy_number}",
                status=copy.status,
                owner=copy.holder_name,
                date_value=copy.issued_at,
                due_value=copy.due_back_at,
                context=copy.location_text,
                target_path=f"library/{manual.id}?tab=distribution&copy={copy.id}",
                details={"copy_number": copy.copy_number, "format": copy.format},
            ))

    elif view == "external-sources":
        query = (
            db.query(dm.ExternalDocumentSource, manual_models.Manual)
            .join(manual_models.Manual, manual_models.Manual.id == dm.ExternalDocumentSource.manual_id)
            .filter(dm.ExternalDocumentSource.tenant_id == tenant.amo_id)
        )
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(or_(
                *_manual_search_conditions(needle),
                dm.ExternalDocumentSource.provider.ilike(needle),
                dm.ExternalDocumentSource.authority.ilike(needle),
                dm.ExternalDocumentSource.subscription_reference.ilike(needle),
            ))
        if wanted_status:
            query = query.filter(dm.ExternalDocumentSource.status == wanted_status)
        if start:
            query = query.filter(dm.ExternalDocumentSource.next_check_due_at >= start)
        if end:
            query = query.filter(dm.ExternalDocumentSource.next_check_due_at <= end)
        query = query.order_by(dm.ExternalDocumentSource.next_check_due_at.asc().nullslast(), dm.ExternalDocumentSource.id.asc())
        total, rows = _paginate(query, page, per_page)
        source_ids = [source.id for source, _manual in rows]
        latest_receipts: dict[str, dm.ExternalRevisionReceipt] = {}
        receipts = (
            db.query(dm.ExternalRevisionReceipt)
            .filter(dm.ExternalRevisionReceipt.source_id.in_(source_ids or ["-"]))
            .order_by(dm.ExternalRevisionReceipt.received_at.desc(), dm.ExternalRevisionReceipt.id.desc())
            .all()
        )
        for receipt in receipts:
            latest_receipts.setdefault(receipt.source_id, receipt)
        for source, manual in rows:
            receipt = latest_receipts.get(source.id)
            status_value = receipt.currency_status if receipt else source.status
            items.append(_item(
                record_id=source.id,
                kind="EXTERNAL_SOURCE",
                manual=manual,
                record=source.provider,
                status=status_value,
                date_value=source.last_checked_at,
                due_value=source.next_check_due_at,
                context=receipt.revision_label if receipt else source.authority or "No revision receipt recorded",
                target_path="compliance?view=external-sources",
                details={
                    "authority": source.authority,
                    "subscription_reference": source.subscription_reference,
                    "received_revision": receipt.revision_label if receipt else None,
                    "applicability_status": receipt.applicability_status if receipt else None,
                },
            ))

    elif view == "review-due":
        query = (
            db.query(dm.DocumentReviewPlan, manual_models.Manual, account_models.User)
            .join(manual_models.Manual, manual_models.Manual.id == dm.DocumentReviewPlan.manual_id)
            .outerjoin(account_models.User, account_models.User.id == dm.DocumentReviewPlan.owner_user_id)
            .filter(dm.DocumentReviewPlan.tenant_id == tenant.amo_id)
        )
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(or_(*_manual_search_conditions(needle), account_models.User.full_name.ilike(needle)))
        if wanted_status:
            query = query.filter(dm.DocumentReviewPlan.status == wanted_status)
        if start:
            query = query.filter(dm.DocumentReviewPlan.due_at >= start)
        if end:
            query = query.filter(dm.DocumentReviewPlan.due_at <= end)
        query = query.order_by(dm.DocumentReviewPlan.due_at.asc())
        total, rows = _paginate(query, page, per_page)
        for review, manual, owner in rows:
            items.append(_item(
                record_id=review.id,
                kind="REVIEW",
                manual=manual,
                record="Periodic document review",
                status=review.status,
                owner=owner.full_name if owner else "Unassigned",
                date_value=review.completed_at,
                due_value=review.due_at,
                context=review.outcome or "Outcome pending",
                target_path=f"library/{manual.id}?tab=compliance",
            ))

    elif view == "temporary-revisions":
        query = (
            db.query(dm.DocumentTemporaryRevision, manual_models.Manual)
            .join(manual_models.Manual, manual_models.Manual.id == dm.DocumentTemporaryRevision.manual_id)
            .filter(dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id)
        )
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(or_(
                *_manual_search_conditions(needle),
                dm.DocumentTemporaryRevision.tr_number.ilike(needle),
                dm.DocumentTemporaryRevision.title.ilike(needle),
                dm.DocumentTemporaryRevision.reason.ilike(needle),
            ))
        if wanted_status:
            query = query.filter(dm.DocumentTemporaryRevision.status == wanted_status)
        if date_from:
            query = query.filter(dm.DocumentTemporaryRevision.effective_date >= date_from)
        if date_to:
            query = query.filter(dm.DocumentTemporaryRevision.expiry_date <= date_to)
        query = query.order_by(dm.DocumentTemporaryRevision.expiry_date.asc())
        total, rows = _paginate(query, page, per_page)
        for tr, manual in rows:
            items.append(_item(
                record_id=tr.id,
                kind="TEMPORARY_REVISION",
                manual=manual,
                record=f"{tr.tr_number} · {tr.title}",
                status=tr.status,
                date_value=tr.effective_date,
                due_value=tr.expiry_date,
                context=tr.approval_status,
                target_path=f"library/{manual.id}?tab=changes&temporary_revision={tr.id}",
            ))

    elif view == "authority":
        query = (
            db.query(dm.DocumentAuthoritySubmission, manual_models.Manual)
            .join(manual_models.Manual, manual_models.Manual.id == dm.DocumentAuthoritySubmission.manual_id)
            .filter(dm.DocumentAuthoritySubmission.tenant_id == tenant.amo_id)
        )
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(or_(
                *_manual_search_conditions(needle),
                dm.DocumentAuthoritySubmission.submission_reference.ilike(needle),
                dm.DocumentAuthoritySubmission.authority_name.ilike(needle),
            ))
        if wanted_status:
            query = query.filter(dm.DocumentAuthoritySubmission.status == wanted_status)
        if start:
            query = query.filter(dm.DocumentAuthoritySubmission.created_at >= start)
        if end:
            query = query.filter(dm.DocumentAuthoritySubmission.created_at <= end)
        query = query.order_by(dm.DocumentAuthoritySubmission.created_at.desc())
        total, rows = _paginate(query, page, per_page)
        for submission, manual in rows:
            items.append(_item(
                record_id=submission.id,
                kind="AUTHORITY",
                manual=manual,
                record=submission.submission_reference,
                status=submission.status,
                date_value=submission.submitted_at or submission.created_at,
                due_value=submission.response_due_at,
                context=submission.authority_name,
                target_path=f"library/{manual.id}?tab=workflow",
                details={"response_summary": submission.response_summary},
            ))

    elif view == "archive":
        query = (
            db.query(manual_models.ManualRevision, manual_models.Manual)
            .join(manual_models.Manual, manual_models.Manual.id == manual_models.ManualRevision.manual_id)
            .filter(
                manual_models.Manual.tenant_id == tenant.id,
                manual_models.ManualRevision.status_enum.in_([
                    manual_models.ManualRevisionStatus.SUPERSEDED,
                    manual_models.ManualRevisionStatus.ARCHIVED,
                ]),
            )
        )
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(or_(
                *_manual_search_conditions(needle),
                manual_models.ManualRevision.rev_number.ilike(needle),
                manual_models.ManualRevision.issue_number.ilike(needle),
            ))
        if wanted_status:
            revision_status = manual_models.ManualRevisionStatus.__members__.get(wanted_status)
            query = query.filter(manual_models.ManualRevision.status_enum == revision_status) if revision_status else query.filter(False)
        if start:
            query = query.filter(manual_models.ManualRevision.created_at >= start)
        if end:
            query = query.filter(manual_models.ManualRevision.created_at <= end)
        query = query.order_by(manual_models.ManualRevision.created_at.desc())
        total, rows = _paginate(query, page, per_page)
        for revision, manual in rows:
            raw_status = str(getattr(revision.status_enum, "value", revision.status_enum or ""))
            items.append(_item(
                record_id=revision.id,
                kind="ARCHIVE",
                manual=manual,
                record=f"Rev {revision.rev_number}",
                status=raw_status,
                date_value=revision.created_at,
                context=f"Superseded by {revision.superseded_by_rev_id}" if revision.superseded_by_rev_id else "Archived revision",
                target_path=f"library/{manual.id}?tab=history",
            ))

    elif view == "change-history":
        query = (
            db.query(dm.DocumentChangeRequest, manual_models.Manual, account_models.User)
            .join(manual_models.Manual, manual_models.Manual.id == dm.DocumentChangeRequest.manual_id)
            .outerjoin(account_models.User, account_models.User.id == dm.DocumentChangeRequest.owner_user_id)
            .filter(dm.DocumentChangeRequest.tenant_id == tenant.amo_id)
        )
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(or_(
                *_manual_search_conditions(needle),
                dm.DocumentChangeRequest.title.ilike(needle),
                dm.DocumentChangeRequest.description.ilike(needle),
                account_models.User.full_name.ilike(needle),
            ))
        if wanted_status:
            query = query.filter(dm.DocumentChangeRequest.status == wanted_status)
        if start:
            query = query.filter(dm.DocumentChangeRequest.created_at >= start)
        if end:
            query = query.filter(dm.DocumentChangeRequest.created_at <= end)
        query = query.order_by(dm.DocumentChangeRequest.created_at.desc())
        total, rows = _paginate(query, page, per_page)
        for change, manual, owner in rows:
            items.append(_item(
                record_id=change.id,
                kind="CHANGE",
                manual=manual,
                record=change.title,
                status=change.status,
                owner=owner.full_name if owner else None,
                date_value=change.closed_at or change.created_at,
                due_value=change.due_at,
                context=change.priority,
                target_path=f"library/{manual.id}?tab=changes",
            ))

    else:  # retention
        query = (
            db.query(km.DocumentationRecord, manual_models.Manual)
            .join(manual_models.Manual, manual_models.Manual.id == km.DocumentationRecord.template_manual_id)
            .filter(km.DocumentationRecord.tenant_id == tenant.amo_id)
        )
        if q and q.strip():
            needle = f"%{q.strip()}%"
            query = query.filter(or_(
                *_manual_search_conditions(needle),
                km.DocumentationRecord.record_number.ilike(needle),
                km.DocumentationRecord.artifact_filename.ilike(needle),
            ))
        if wanted_status:
            query = query.filter(km.DocumentationRecord.status == wanted_status)
        if start:
            query = query.filter(km.DocumentationRecord.submitted_at >= start)
        if end:
            query = query.filter(km.DocumentationRecord.submitted_at <= end)
        query = query.order_by(km.DocumentationRecord.submitted_at.desc())
        total, rows = _paginate(query, page, per_page)
        for record, manual in rows:
            items.append(_item(
                record_id=record.id,
                kind="RETENTION_RECORD",
                manual=manual,
                record=record.record_number,
                status=record.status,
                date_value=record.submitted_at,
                context=f"{record.retention_years or 'Default'} years · {record.retention_disposition}",
                target_path=f"library/{manual.id}?tab=history&record={record.id}",
                details={"artifact_filename": record.artifact_filename, "retention_years": record.retention_years, "disposition": record.retention_disposition},
            ))

    return {
        "view": view,
        "generated_at": utcnow().isoformat(),
        "items": items,
        "pagination": {"page": page, "per_page": per_page, "total": total, "returned": len(items)},
    }
