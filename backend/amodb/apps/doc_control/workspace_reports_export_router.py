from __future__ import annotations

import csv
import io
import json
import re
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from .workspace_reports_portfolio_router import get_reports_portfolio
from .workspace_reports_register_router import REPORT_VIEWS, get_reports_register
from .workspace_service import require_control_user, resolve_tenant, utcnow


router = APIRouter(prefix="/workspace", tags=["Document Control Evidence Exports"])

EXPORT_MAX_ROWS = 10_000
EXPORT_BATCH_SIZE = 100


def _safe_csv_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if re.match(r"^\s*[=+\-@]", text):
        return f"'{text}"
    return text


def _revision_label(value: dict[str, Any] | None) -> str:
    if not value:
        return ""
    issue = str(value.get("issue_number") or "").strip()
    revision = str(value.get("revision_number") or value.get("rev_number") or "").strip()
    if not issue and not revision:
        return ""
    return f"{'Issue ' + issue + ' · ' if issue else ''}Rev {revision or '—'}"


def _csv_response(*, filename: str, headings: list[str], rows: list[list[Any]], generated_at: str) -> Response:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow([_safe_csv_value(value) for value in headings])
    for row in rows:
        writer.writerow([_safe_csv_value(value) for value in row])
    payload = stream.getvalue()
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Document-Control-Export-Rows": str(len(rows)),
            "X-Document-Control-Generated-At": generated_at,
        },
    )


def _require_export_bound(total: int) -> None:
    if total <= EXPORT_MAX_ROWS:
        return
    raise HTTPException(
        status_code=422,
        detail={
            "code": "DOCUMENT_CONTROL_EXPORT_LIMIT_EXCEEDED",
            "message": (
                f"The filtered evidence register contains {total} rows, above the "
                f"{EXPORT_MAX_ROWS}-row direct export limit. Narrow the filters before exporting."
            ),
            "total": total,
            "limit": EXPORT_MAX_ROWS,
        },
    )


def _master_rows(
    *,
    tenant_slug: str,
    q: str | None,
    document_class: str | None,
    lifecycle_status: str | None,
    db: Session,
    current_user: account_models.User,
) -> tuple[str, list[list[Any]]]:
    first = get_reports_portfolio(
        tenant_slug=tenant_slug,
        q=q,
        document_class=document_class,
        lifecycle_status=lifecycle_status,
        page=1,
        per_page=EXPORT_BATCH_SIZE,
        db=db,
        current_user=current_user,
    )
    total = int(first["pagination"]["total"])
    _require_export_bound(total)
    items = list(first["items"])
    page = 2
    while len(items) < total:
        chunk = get_reports_portfolio(
            tenant_slug=tenant_slug,
            q=q,
            document_class=document_class,
            lifecycle_status=lifecycle_status,
            page=page,
            per_page=EXPORT_BATCH_SIZE,
            db=db,
            current_user=current_user,
        )
        returned = list(chunk["items"])
        if not returned:
            break
        items.extend(returned)
        page += 1
    if len(items) != total:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DOCUMENT_CONTROL_EXPORT_CHANGED_DURING_GENERATION",
                "message": "The controlled register changed while the export was being generated. Refresh and retry.",
                "expected_rows": total,
                "generated_rows": len(items),
            },
        )
    rows = [
        [
            item.get("manual_id"),
            item.get("code"),
            item.get("title"),
            item.get("manual_type"),
            item.get("document_class"),
            item.get("owner_department"),
            item.get("lifecycle_status"),
            _revision_label(item.get("latest_revision")),
            _revision_label(item.get("effective_revision")),
            item.get("next_review_due"),
            "YES" if item.get("regulated") else "NO",
            "YES" if item.get("restricted") else "NO",
        ]
        for item in items
    ]
    return str(first["generated_at"]), rows


def _register_rows(
    *,
    tenant_slug: str,
    view: str,
    q: str | None,
    status: str | None,
    date_from: date | None,
    date_to: date | None,
    db: Session,
    current_user: account_models.User,
) -> tuple[str, list[list[Any]]]:
    first = get_reports_register(
        tenant_slug=tenant_slug,
        view=view,
        q=q,
        status=status,
        date_from=date_from,
        date_to=date_to,
        page=1,
        per_page=EXPORT_BATCH_SIZE,
        db=db,
        current_user=current_user,
    )
    total = int(first["pagination"]["total"])
    _require_export_bound(total)
    items = list(first["items"])
    page = 2
    while len(items) < total:
        chunk = get_reports_register(
            tenant_slug=tenant_slug,
            view=view,
            q=q,
            status=status,
            date_from=date_from,
            date_to=date_to,
            page=page,
            per_page=EXPORT_BATCH_SIZE,
            db=db,
            current_user=current_user,
        )
        returned = list(chunk["items"])
        if not returned:
            break
        items.extend(returned)
        page += 1
    if len(items) != total:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DOCUMENT_CONTROL_EXPORT_CHANGED_DURING_GENERATION",
                "message": "The evidence register changed while the export was being generated. Refresh and retry.",
                "expected_rows": total,
                "generated_rows": len(items),
            },
        )
    rows = [
        [
            item.get("id"),
            item.get("kind"),
            (item.get("document") or {}).get("id"),
            (item.get("document") or {}).get("code"),
            (item.get("document") or {}).get("title"),
            item.get("record"),
            item.get("status"),
            item.get("owner"),
            item.get("date"),
            item.get("due_at"),
            item.get("context"),
            item.get("target_path"),
            json.dumps(item.get("details") or {}, sort_keys=True, separators=(",", ":")),
        ]
        for item in items
    ]
    return str(first["generated_at"]), rows


@router.get("/t/{tenant_slug}/reports-export.csv")
def export_filtered_evidence_register(
    tenant_slug: str,
    view: str = Query(
        default="master",
        pattern="^(master|revisions|lep|distribution|acknowledgements|controlled-copies|external-sources|review-due|temporary-revisions|authority|archive|change-history|retention)$",
    ),
    q: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None, max_length=48),
    document_class: str | None = Query(default=None, max_length=32),
    lifecycle_status: str | None = Query(default=None, max_length=32),
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Generate the complete filtered evidence register on the server.

    Interactive reports remain paginated. Export is explicit, tenant-scoped and
    bounded to EXPORT_MAX_ROWS. The server rejects larger result sets rather than
    returning a silently truncated browser page.
    """
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    generated_at = utcnow().isoformat()

    if view == "master":
        source_generated_at, rows = _master_rows(
            tenant_slug=tenant_slug,
            q=q,
            document_class=document_class,
            lifecycle_status=lifecycle_status,
            db=db,
            current_user=current_user,
        )
        headings = [
            "Document ID",
            "Code",
            "Title",
            "Type",
            "Class",
            "Owner Department",
            "Lifecycle",
            "Latest Revision",
            "Effective Revision",
            "Next Review",
            "Regulated",
            "Restricted",
        ]
    else:
        if view not in REPORT_VIEWS:
            raise HTTPException(status_code=422, detail="Unsupported evidence register")
        source_generated_at, rows = _register_rows(
            tenant_slug=tenant_slug,
            view=view,
            q=q,
            status=status,
            date_from=date_from,
            date_to=date_to,
            db=db,
            current_user=current_user,
        )
        headings = [
            "Record ID",
            "Record Type",
            "Document ID",
            "Document Code",
            "Document Title",
            "Record",
            "Status",
            "Owner",
            "Date",
            "Due / Expiry",
            "Context",
            "Source Path",
            "Details JSON",
        ]

    safe_view = re.sub(r"[^a-z0-9_-]+", "-", view.lower()).strip("-") or "register"
    filename = f"document-control-{tenant.slug}-{safe_view}-{generated_at[:10]}.csv"
    return _csv_response(
        filename=filename,
        headings=headings,
        rows=rows,
        generated_at=source_generated_at or generated_at,
    )
