from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, and_, cast, exists, func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import governance_models as gm
from . import knowledge_models as km
from .workspace_library_router import _scope_match
from .workspace_service import is_control_user, resolve_tenant, role_value, utcnow


router = APIRouter(prefix="/workspace", tags=["Document Control Library Discovery"])
ACTIVE_REVIEW_STATUSES = {"SCHEDULED", "IN_PROGRESS"}


def _revision_status(row: manual_models.ManualRevision | None) -> str | None:
    if not row:
        return None
    return str(getattr(row.status_enum, "value", row.status_enum or ""))


def _serialize_revision(row: manual_models.ManualRevision | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row.id,
        "issue_number": row.issue_number,
        "revision_number": row.rev_number,
        "status": _revision_status(row),
        "effective_date": row.effective_date.isoformat() if row.effective_date else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "source_filename": row.source_filename,
        "page_count": row.source_page_count,
    }


@router.get("/t/{tenant_slug}/library-discovery")
def library_discovery(
    tenant_slug: str,
    view: str = Query(default="all", pattern="^(all|my-documents|favorites|recently-opened|recently-revised|awaiting-my-review|external-technical-data|due-for-review|superseded|archived)$"),
    q: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return a bounded permission-filtered discovery view for the company library."""
    tenant = resolve_tenant(db, tenant_slug, current_user)
    controller = is_control_user(current_user)
    query = (
        db.query(manual_models.Manual, dm.DocumentControlProfile)
        .outerjoin(
            dm.DocumentControlProfile,
            and_(
                dm.DocumentControlProfile.manual_id == manual_models.Manual.id,
                dm.DocumentControlProfile.tenant_id == tenant.amo_id,
            ),
        )
        .filter(manual_models.Manual.tenant_id == tenant.id)
    )

    if not controller:
        profile = dm.DocumentControlProfile
        access_conditions = [
            profile.id.is_(None),
            profile.restricted_flag.is_(False),
            _scope_match(profile.access_scope_json, "user_ids", str(current_user.id)),
        ]
        current_role = role_value(current_user)
        if current_role:
            access_conditions.append(_scope_match(profile.access_scope_json, "roles", current_role, case_insensitive=True))
        department_code = getattr(getattr(current_user, "department", None), "code", None)
        if department_code:
            access_conditions.append(_scope_match(profile.access_scope_json, "departments", str(department_code), case_insensitive=True))
        query = query.filter(or_(*access_conditions))

    if q and q.strip():
        needle = f"%{q.strip()}%"
        matching_revision = exists().where(and_(
            manual_models.ManualRevision.manual_id == manual_models.Manual.id,
            or_(
                manual_models.ManualRevision.rev_number.ilike(needle),
                manual_models.ManualRevision.issue_number.ilike(needle),
                manual_models.ManualRevision.source_filename.ilike(needle),
            ),
        ))
        matching_node = exists().where(and_(
            km.DocumentationNode.tenant_id == tenant.amo_id,
            km.DocumentationNode.manual_id == manual_models.Manual.id,
            or_(
                km.DocumentationNode.code.ilike(needle),
                km.DocumentationNode.title.ilike(needle),
                km.DocumentationNode.path.ilike(needle),
                cast(km.DocumentationNode.metadata_json, String).ilike(needle),
            ),
        ))
        matching_owner = exists().where(and_(
            account_models.User.id == dm.DocumentControlProfile.owner_user_id,
            or_(account_models.User.full_name.ilike(needle), account_models.User.email.ilike(needle)),
        ))
        matching_indexed_content = exists().where(and_(
            manual_models.ManualRevision.manual_id == manual_models.Manual.id,
            manual_models.ManualSection.revision_id == manual_models.ManualRevision.id,
            manual_models.ManualBlock.section_id == manual_models.ManualSection.id,
            or_(manual_models.ManualSection.heading.ilike(needle), manual_models.ManualBlock.text_plain.ilike(needle)),
        ))
        query = query.filter(or_(
            manual_models.Manual.code.ilike(needle),
            manual_models.Manual.title.ilike(needle),
            manual_models.Manual.manual_type.ilike(needle),
            dm.DocumentControlProfile.owner_department.ilike(needle),
            matching_revision,
            matching_node,
            matching_owner,
            matching_indexed_content,
        ))

    ordering = (manual_models.Manual.code.asc(), manual_models.Manual.id.asc())
    progress_subquery = None
    revision_activity_subquery = None

    if view == "my-documents":
        assigned = exists().where(and_(
            gm.DocumentResponsibilityAssignment.tenant_id == tenant.amo_id,
            gm.DocumentResponsibilityAssignment.manual_id == manual_models.Manual.id,
            gm.DocumentResponsibilityAssignment.assignee_user_id == str(current_user.id),
            gm.DocumentResponsibilityAssignment.responsibility_type.in_(["DOCUMENT_OWNER", "BUSINESS_OWNER"]),
        ))
        query = query.filter(or_(dm.DocumentControlProfile.owner_user_id == str(current_user.id), assigned))
    elif view in {"favorites", "recently-opened"}:
        progress_query = db.query(
            manual_models.ManualReaderProgress.manual_id.label("manual_id"),
            func.max(manual_models.ManualReaderProgress.last_opened_at).label("last_opened_at"),
        ).filter(manual_models.ManualReaderProgress.user_id == str(current_user.id))
        if view == "favorites":
            progress_query = progress_query.filter(manual_models.ManualReaderProgress.bookmark_label.isnot(None))
        progress_subquery = progress_query.group_by(manual_models.ManualReaderProgress.manual_id).subquery()
        query = query.join(progress_subquery, progress_subquery.c.manual_id == manual_models.Manual.id)
        ordering = (progress_subquery.c.last_opened_at.desc(), manual_models.Manual.code.asc())
    elif view == "recently-revised":
        revision_activity_subquery = (
            db.query(
                manual_models.ManualRevision.manual_id.label("manual_id"),
                func.max(func.coalesce(manual_models.ManualRevision.published_at, manual_models.ManualRevision.created_at)).label("revision_activity_at"),
            )
            .group_by(manual_models.ManualRevision.manual_id)
            .subquery()
        )
        query = query.join(revision_activity_subquery, revision_activity_subquery.c.manual_id == manual_models.Manual.id)
        ordering = (revision_activity_subquery.c.revision_activity_at.desc(), manual_models.Manual.code.asc())
    elif view == "awaiting-my-review":
        query = query.filter(exists().where(and_(
            dm.DocumentReviewPlan.tenant_id == tenant.amo_id,
            dm.DocumentReviewPlan.manual_id == manual_models.Manual.id,
            dm.DocumentReviewPlan.owner_user_id == str(current_user.id),
            dm.DocumentReviewPlan.status.in_(ACTIVE_REVIEW_STATUSES),
        )))
    elif view == "external-technical-data":
        query = query.filter(or_(
            dm.DocumentControlProfile.document_class == "EXTERNAL",
            exists().where(and_(
                km.DocumentationNode.tenant_id == tenant.amo_id,
                km.DocumentationNode.manual_id == manual_models.Manual.id,
                km.DocumentationNode.node_type == "EXTERNAL_DOCUMENT",
                km.DocumentationNode.status == "ACTIVE",
            )),
        ))
    elif view == "due-for-review":
        query = query.filter(or_(
            dm.DocumentControlProfile.next_review_due <= date.today(),
            exists().where(and_(
                dm.DocumentReviewPlan.tenant_id == tenant.amo_id,
                dm.DocumentReviewPlan.manual_id == manual_models.Manual.id,
                dm.DocumentReviewPlan.status.in_(ACTIVE_REVIEW_STATUSES),
                dm.DocumentReviewPlan.due_at <= utcnow(),
            )),
        ))
    elif view == "superseded":
        query = query.filter(or_(
            manual_models.Manual.status == "SUPERSEDED",
            exists().where(and_(
                manual_models.ManualRevision.manual_id == manual_models.Manual.id,
                manual_models.ManualRevision.status_enum == manual_models.ManualRevisionStatus.SUPERSEDED,
            )),
        ))
    elif view == "archived":
        query = query.filter(or_(
            manual_models.Manual.status == "ARCHIVED",
            exists().where(and_(
                manual_models.ManualRevision.manual_id == manual_models.Manual.id,
                manual_models.ManualRevision.status_enum == manual_models.ManualRevisionStatus.ARCHIVED,
            )),
        ))

    total = int(query.order_by(None).count())
    selected = query.order_by(*ordering).offset((page - 1) * per_page).limit(per_page).all()
    manuals = [manual for manual, _profile in selected]
    profiles = {manual.id: profile for manual, profile in selected}
    manual_ids = [manual.id for manual in manuals]

    revisions = (
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.manual_id.in_(manual_ids or ["-"]))
        .order_by(manual_models.ManualRevision.created_at.desc(), manual_models.ManualRevision.id.desc())
        .all()
    )
    latest_by_manual: dict[str, manual_models.ManualRevision] = {}
    by_id: dict[str, manual_models.ManualRevision] = {}
    for revision in revisions:
        latest_by_manual.setdefault(revision.manual_id, revision)
        by_id[revision.id] = revision

    nodes = {
        row.manual_id: row
        for row in db.query(km.DocumentationNode).filter(
            km.DocumentationNode.tenant_id == tenant.amo_id,
            km.DocumentationNode.manual_id.in_(manual_ids or ["-"]),
            km.DocumentationNode.status == "ACTIVE",
        ).all()
    }
    owner_ids = {profile.owner_user_id for profile in profiles.values() if profile and profile.owner_user_id}
    owners = {
        row.id: row
        for row in db.query(account_models.User).filter(account_models.User.id.in_(owner_ids or ["-"])).all()
    }
    progress_rows = (
        db.query(manual_models.ManualReaderProgress)
        .filter(
            manual_models.ManualReaderProgress.user_id == str(current_user.id),
            manual_models.ManualReaderProgress.manual_id.in_(manual_ids or ["-"]),
        )
        .order_by(manual_models.ManualReaderProgress.last_opened_at.desc())
        .all()
    )
    progress_by_manual: dict[str, manual_models.ManualReaderProgress] = {}
    for progress in progress_rows:
        progress_by_manual.setdefault(progress.manual_id, progress)

    items = []
    for manual in manuals:
        profile = profiles.get(manual.id)
        latest = latest_by_manual.get(manual.id)
        current = by_id.get(manual.current_published_rev_id or "")
        read_target = current if current and current.status_enum == manual_models.ManualRevisionStatus.PUBLISHED else latest if controller else None
        node = nodes.get(manual.id)
        owner = owners.get(profile.owner_user_id) if profile and profile.owner_user_id else None
        progress = progress_by_manual.get(manual.id)
        items.append({
            "id": manual.id,
            "code": manual.code,
            "title": manual.title,
            "manual_type": manual.manual_type,
            "lifecycle_status": manual.status,
            "document_class": profile.document_class if profile else "INTERNAL",
            "owner": {
                "id": owner.id if owner else profile.owner_user_id if profile else None,
                "name": owner.full_name if owner else None,
                "department": profile.owner_department if profile else manual.owner_role,
            },
            "node": {
                "type": node.node_type if node else "MANUAL",
                "path": node.path if node else None,
            },
            "current_revision": _serialize_revision(current),
            "latest_revision": _serialize_revision(latest),
            "read_target_revision_id": read_target.id if read_target else None,
            "next_review_due": profile.next_review_due.isoformat() if profile and profile.next_review_due else None,
            "last_opened_at": progress.last_opened_at.isoformat() if progress and progress.last_opened_at else None,
            "favorite": bool(progress and progress.bookmark_label),
        })

    return {
        "view": view,
        "items": items,
        "capabilities": {"read": True, "control": controller},
        "pagination": {"page": page, "per_page": per_page, "total": total, "returned": len(items)},
    }
