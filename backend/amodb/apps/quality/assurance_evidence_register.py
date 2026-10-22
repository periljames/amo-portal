"""Read-only Evidence Vault index over the governed evidence stores."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from sqlalchemy import DateTime, Integer, String, cast, column, func, inspect, literal, or_, select, table, union_all
from sqlalchemy.orm import Session

from amodb.database import get_read_db
from . import models
from .audit_evidence_models import QualityAuditEvidenceArtifact as AuditFile
from .audit_archive_governance_models import QualityAuditArchiveManifest as Archive, QualityAuditDispositionEvent as Disposition
from .people_authorization_models import QualityAuthorizationEvidence as AuthorizationFile, QualityAuthorizationCase as AuthorizationCase
from .people_models import QualityPrivilege
from .people_authorization_router import _can_view_tenant_authorization_register
from .tenant_security import TenantContext, has_quality_permission, require_quality_permission, set_postgres_tenant_context

router = APIRouter(prefix="/evidence-vault", tags=["Quality evidence register"])


def read_evidence_register(db: Session, ctx: TenantContext, *, archives=False, q=None, status=None, limit=30, offset=0):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    available = set(inspect(db.connection()).get_table_names())
    sources, source_errors = [], []
    def add(label, tables, statement):
        if set(tables) <= available:
            sources.append(statement)
        else:
            source_errors.append({"label": label, "message": "This evidence source is unavailable."})
    def fields(kind, identity, filename, reference, created, size, checksum, origin, source):
        return [
            (literal(kind + ":") + cast(identity, String)).label("id"), cast(identity, String).label("file_id"),
            filename.label("filename"), literal(source).label("source"), reference.label("reference"),
            created.label("created_at"), size.label("size_bytes"), checksum.label("sha256"),
            cast(origin, String).label("origin_id"), literal(kind).label("kind"), literal("AVAILABLE").label("status"),
        ]
    Audit, Car, Finding = models.QMSAudit, models.CorrectiveActionRequest, models.QMSAuditFinding
    if archives:
        if has_quality_permission(db, ctx, "qms.audit.view"):
            disposed = select(Disposition.id).where(Disposition.amo_id == ctx.amo_id, Disposition.manifest_id == Archive.id, Disposition.event_type == "EXECUTED").exists()
            add("Audit archives", [Archive.__tablename__, Disposition.__tablename__, Audit.__tablename__],
                select(*fields("archive", Archive.id, Archive.package_filename, Audit.audit_ref, Archive.created_at, Archive.package_size_bytes, Archive.package_sha256, Archive.audit_id, "Audit archive"))
                .select_from(Archive).join(Audit, Audit.id == Archive.audit_id).where(Archive.amo_id == ctx.amo_id, Audit.amo_id == ctx.amo_id, Archive.package_file_ref.is_not(None), Archive.package_sha256.is_not(None), ~disposed))
    else:
        if has_quality_permission(db, ctx, "qms.audit.view"):
            add("Audit evidence", [AuditFile.__tablename__, Audit.__tablename__],
                select(*fields("audit", AuditFile.id, AuditFile.filename, Audit.audit_ref, AuditFile.created_at, AuditFile.size_bytes, AuditFile.sha256, AuditFile.audit_id, "Audit evidence"))
                .select_from(AuditFile).join(Audit, Audit.id == AuditFile.audit_id).where(AuditFile.amo_id == ctx.amo_id, Audit.amo_id == ctx.amo_id, Audit.deleted_at.is_(None), AuditFile.server_processing_state == "AVAILABLE", AuditFile.offline_upload_state == "SYNCED"))
        if has_quality_permission(db, ctx, "qms.finding.view"):
            File = models.QMSFindingAttachment
            add("Finding evidence", [File.__tablename__, Finding.__tablename__, Audit.__tablename__],
                select(*fields("finding", File.id, File.filename, Finding.finding_ref, File.uploaded_at, File.size_bytes, File.sha256, Finding.id, "Finding evidence"))
                .select_from(File).join(Finding, Finding.id == File.finding_id).join(Audit, Audit.id == Finding.audit_id)
                .where(Finding.amo_id == ctx.amo_id, Audit.amo_id == ctx.amo_id, Audit.deleted_at.is_(None)))
        if has_quality_permission(db, ctx, "qms.car.view"):
            File = models.CARAttachment
            add("CAR evidence", [File.__tablename__, Car.__tablename__],
                select(*fields("car", File.id, File.filename, Car.car_number, File.uploaded_at, File.size_bytes, File.sha256, Car.id, "CAR evidence"))
                .select_from(File).join(Car, Car.id == File.car_id).where(Car.amo_id == ctx.amo_id, Car.program == models.CARProgram.QUALITY))
        if has_quality_permission(db, ctx, "qms.people.view"):
            File = AuthorizationFile
            owner = func.coalesce(AuthorizationCase.user_id, QualityPrivilege.user_id)
            reference = func.coalesce(AuthorizationCase.person_snapshot["name"].as_string(), File.label)
            query = select(*fields("authorization", File.id, func.coalesce(File.original_filename, File.label), reference, File.created_at, File.size_bytes, File.sha256, File.case_id, "Authorization evidence"))
            query = query.select_from(File).outerjoin(AuthorizationCase, (AuthorizationCase.id == File.case_id) & (AuthorizationCase.amo_id == ctx.amo_id)).outerjoin(QualityPrivilege, (QualityPrivilege.id == File.privilege_id) & (QualityPrivilege.amo_id == ctx.amo_id))
            query = query.where(File.amo_id == ctx.amo_id, File.status == "ACTIVE", File.storage_path.is_not(None), or_(File.case_id.is_(None), AuthorizationCase.id.is_not(None)), or_(File.privilege_id.is_(None), QualityPrivilege.id.is_not(None)))
            if not _can_view_tenant_authorization_register(db, ctx):
                query = query.where(owner == ctx.user_id)
            add("Authorization evidence", [File.__tablename__, AuthorizationCase.__tablename__, QualityPrivilege.__tablename__], query)
        if "qms_evidence_files" in available:
            legacy_columns = {item["name"] for item in inspect(db.connection()).get_columns("qms_evidence_files")}
            legacy = table("qms_evidence_files", *[column(name) for name in legacy_columns])
            filename = func.coalesce(*[legacy.c[name] for name in ["filename", "original_filename", "name", "title"] if name in legacy_columns], cast(legacy.c.id, String))
            created = legacy.c.created_at if "created_at" in legacy_columns else cast(literal(None), DateTime(timezone=True))
            checksum = legacy.c.sha256 if "sha256" in legacy_columns else cast(literal(None), String)
            size = legacy.c.size_bytes if "size_bytes" in legacy_columns else cast(literal(None), Integer)
            query = select(*fields("legacy", legacy.c.id, filename, literal("Retained evidence"), created, size, checksum, legacy.c.id, "Retained evidence")).where(legacy.c.amo_id == ctx.amo_id)
            if "deleted_at" in legacy_columns:
                query = query.where(legacy.c.deleted_at.is_(None))
            sources.append(query)

    base = "/maintenance/" + quote(ctx.amo_code, safe="") + "/quality"
    api = "/api" + base
    columns = ["filename", "source", "reference", "created_at", "size_bytes"]
    result = {"items": [], "columns": columns, "total": 0, "limit": limit, "offset": offset, "next_offset": None, "has_more": False, "source_errors": source_errors}
    if not sources:
        return result
    population = union_all(*sources).subquery()
    predicates = []
    if q:
        match = "%" + q.strip() + "%"
        predicates.append(or_(population.c.filename.ilike(match), population.c.reference.ilike(match), population.c.source.ilike(match)))
    if status:
        predicates.append(population.c.status == status.upper())
    total = db.scalar(select(func.count()).select_from(population).where(*predicates)) or 0
    rows = db.execute(select(population).where(*predicates).order_by(population.c.created_at.desc(), population.c.id).offset(offset).limit(limit)).mappings()
    items = []
    for record in rows:
        item = dict(record)
        identity, origin, kind = quote(item.pop("file_id"), safe=""), quote(item.pop("origin_id") or "", safe=""), item.pop("kind")
        if kind == "audit":
            item.update(download_url=f"{api}/audits/{origin}/evidence/{identity}/download", source_route=f"{base}/audits/{origin}/live")
        elif kind == "finding":
            item.update(download_url=f"/api/quality/findings/{origin}/attachments/{identity}/download", source_route=f"{base}/findings/{origin}/overview")
        elif kind == "car":
            item.update(download_url=f"/api/quality/cars/{origin}/attachments/{identity}/download", source_route=f"{base}/cars/{origin}/overview")
        elif kind == "authorization":
            item.update(download_url=f"{api}/people/authorization-control/evidence/{identity}/download", source_route=f"{base}?workspace=people&tab=cases&case={origin}" if origin else f"{base}?workspace=people")
        elif kind == "archive":
            item.update(download_url=f"{api}/audits/{origin}/archive-manifests/{identity}/download", source_route=f"{base}/audits/{origin}/archive")
        else:
            item.update(download_url=f"{api}/evidence-vault/files/{identity}/download")
        items.append(item)
    result.update(items=items, total=int(total), has_more=offset + len(items) < total, next_offset=offset + len(items) if offset + len(items) < total else None)
    return result


@router.get("/search")
@router.get("/files")
def evidence_files(q: str | None = Query(default=None, max_length=160), status: str | None = None,
                   limit: int = Query(default=30, ge=1, le=100), offset: int = Query(default=0, ge=0),
                   ctx: TenantContext = Depends(require_quality_permission("qms.evidence.view")), db: Session = Depends(get_read_db)):
    return read_evidence_register(db, ctx, q=q, status=status, limit=limit, offset=offset)


@router.get("/audit-packages")
@router.get("/immutable-archive")
def archive_packages(q: str | None = Query(default=None, max_length=160), status: str | None = None,
                     limit: int = Query(default=30, ge=1, le=100), offset: int = Query(default=0, ge=0),
                     ctx: TenantContext = Depends(require_quality_permission("qms.evidence.view")), db: Session = Depends(get_read_db)):
    return read_evidence_register(db, ctx, archives=True, q=q, status=status, limit=limit, offset=offset)
