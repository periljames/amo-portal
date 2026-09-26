from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.manuals import models as manual_models

from . import domain_models as dm
from . import governance_models as gm
from . import library_models as lm
from . import records_vault_models as rm
from . import warehouse_models as wm


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()


def _as_datetime(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _safe_code(value: Any, *, fallback: str) -> str:
    text = " ".join(str(value or "").strip().split())
    return (text or fallback)[:160]


def _location_code(path_text: str) -> str:
    digest = hashlib.sha256(path_text.strip().upper().encode("utf-8")).hexdigest()[:16].upper()
    return f"LOC-{digest}"


def _next_sequence(db: Session, tenant_id: str, content_record_id: str) -> int:
    current = (
        db.query(func.max(wm.WarehouseContentVersion.sequence))
        .filter(
            wm.WarehouseContentVersion.tenant_id == tenant_id,
            wm.WarehouseContentVersion.content_record_id == content_record_id,
        )
        .scalar()
    )
    return int(current or 0) + 1


def ensure_content_record(
    db: Session,
    *,
    tenant_id: str,
    resource_type: str,
    canonical_code: str,
    title: str,
    source_entity_type: str,
    source_entity_id: str,
    actor_user_id: str | None = None,
    description: str | None = None,
    classification: str = "INTERNAL",
    lifecycle_status: str = "ACTIVE",
    owner_department: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> wm.WarehouseContentRecord:
    row = (
        db.query(wm.WarehouseContentRecord)
        .filter(
            wm.WarehouseContentRecord.tenant_id == tenant_id,
            wm.WarehouseContentRecord.source_entity_type == source_entity_type,
            wm.WarehouseContentRecord.source_entity_id == str(source_entity_id),
        )
        .first()
    )
    if row is None:
        row = wm.WarehouseContentRecord(
            tenant_id=tenant_id,
            resource_type=resource_type,
            canonical_code=_safe_code(canonical_code, fallback=str(source_entity_id)),
            title=title.strip()[:500],
            source_entity_type=source_entity_type,
            source_entity_id=str(source_entity_id),
            created_by_user_id=actor_user_id,
        )
        db.add(row)
        db.flush()

    row.resource_type = resource_type
    row.canonical_code = _safe_code(canonical_code, fallback=str(source_entity_id))
    row.title = title.strip()[:500]
    row.description = (description or "").strip() or None
    row.classification = (classification or "INTERNAL").strip().upper()[:32]
    row.lifecycle_status = (lifecycle_status or "ACTIVE").strip().upper()[:32]
    row.owner_department = (owner_department or "").strip()[:128] or None
    row.metadata_json = {**dict(row.metadata_json or {}), **dict(metadata or {})}
    return row


def ensure_content_version(
    db: Session,
    *,
    tenant_id: str,
    content_record_id: str,
    version_label: str,
    source_version_type: str,
    source_version_id: str,
    actor_user_id: str | None = None,
    lifecycle_status: str = "DRAFT",
    file_hash: str | None = None,
    effective_at: date | datetime | None = None,
    superseded_at: date | datetime | None = None,
    change_summary: str | None = None,
    immutable: bool = False,
    metadata: dict[str, Any] | None = None,
) -> wm.WarehouseContentVersion:
    row = (
        db.query(wm.WarehouseContentVersion)
        .filter(
            wm.WarehouseContentVersion.tenant_id == tenant_id,
            wm.WarehouseContentVersion.source_version_type == source_version_type,
            wm.WarehouseContentVersion.source_version_id == str(source_version_id),
        )
        .first()
    )
    if row is None:
        row = wm.WarehouseContentVersion(
            tenant_id=tenant_id,
            content_record_id=content_record_id,
            version_label=(version_label or "1")[:128],
            sequence=_next_sequence(db, tenant_id, content_record_id),
            source_version_type=source_version_type,
            source_version_id=str(source_version_id),
            created_by_user_id=actor_user_id,
        )
        db.add(row)
        db.flush()

    # Source-backed versions preserve their sequence/source identity while the
    # projection may refresh lifecycle metadata. The source binary itself remains
    # authoritative and is never overwritten by this registry.
    # The version label and source hash are write-once identity. Lifecycle status
    # may move (for example PUBLISHED -> SUPERSEDED) without rewriting the version.
    if not row.version_label:
        row.version_label = (version_label or "1")[:128]
    row.lifecycle_status = (lifecycle_status or "DRAFT").strip().upper()[:32]
    if not row.file_hash and file_hash:
        row.file_hash = str(file_hash).strip()[:64] or None
    row.effective_at = _as_datetime(effective_at)
    row.superseded_at = _as_datetime(superseded_at)
    row.change_summary = (change_summary or "").strip() or None
    row.immutable = bool(immutable)
    row.metadata_json = {**dict(row.metadata_json or {}), **dict(metadata or {})}
    return row


def ensure_binary_object(
    db: Session,
    *,
    tenant_id: str,
    content_version_id: str,
    filename: str,
    mime_type: str,
    sha256: str,
    storage_uri: str,
    object_role: str = "ORIGINAL",
    size_bytes: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> wm.WarehouseBinaryObject:
    row = (
        db.query(wm.WarehouseBinaryObject)
        .filter(
            wm.WarehouseBinaryObject.tenant_id == tenant_id,
            wm.WarehouseBinaryObject.content_version_id == content_version_id,
            wm.WarehouseBinaryObject.sha256 == sha256,
            wm.WarehouseBinaryObject.object_role == object_role,
        )
        .first()
    )
    if row is None:
        row = wm.WarehouseBinaryObject(
            tenant_id=tenant_id,
            content_version_id=content_version_id,
            object_role=object_role,
            filename=filename[:255],
            mime_type=mime_type[:128],
            size_bytes=size_bytes,
            sha256=sha256[:64],
            storage_uri=storage_uri,
            metadata_json=dict(metadata or {}),
        )
        db.add(row)
    return row


def ensure_identifier(
    db: Session,
    *,
    tenant_id: str,
    content_record_id: str,
    scheme: str,
    normalized_value: str,
    display_value: str,
    source: str,
) -> wm.WarehouseIdentifier:
    row = (
        db.query(wm.WarehouseIdentifier)
        .filter(
            wm.WarehouseIdentifier.tenant_id == tenant_id,
            wm.WarehouseIdentifier.scheme == scheme[:32],
            wm.WarehouseIdentifier.normalized_value == normalized_value[:255],
        )
        .first()
    )
    if row is None:
        row = wm.WarehouseIdentifier(
            tenant_id=tenant_id,
            content_record_id=content_record_id,
            scheme=scheme[:32],
            normalized_value=normalized_value[:255],
            display_value=display_value[:255],
            source=source[:64],
        )
        db.add(row)
    return row


def ensure_location(
    db: Session,
    *,
    tenant_id: str,
    path_text: str | None,
    location_type: str = "UNSPECIFIED",
) -> wm.WarehouseLocation | None:
    path = " / ".join(part.strip() for part in str(path_text or "").split("/") if part.strip())
    if not path:
        return None
    code = _location_code(path)
    row = (
        db.query(wm.WarehouseLocation)
        .filter(
            wm.WarehouseLocation.tenant_id == tenant_id,
            wm.WarehouseLocation.code == code,
        )
        .first()
    )
    if row is None:
        row = wm.WarehouseLocation(
            tenant_id=tenant_id,
            code=code,
            name=path.split(" / ")[-1][:255],
            location_type=location_type[:40],
            path_text=path[:1000],
        )
        db.add(row)
        db.flush()
    else:
        row.path_text = path[:1000]
        row.name = path.split(" / ")[-1][:255]
    return row


def record_event(
    db: Session,
    *,
    tenant_id: str,
    content_record_id: str,
    event_type: str,
    actor_user_id: str | None = None,
    content_version_id: str | None = None,
    item_copy_id: str | None = None,
    transaction_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> wm.WarehouseAuditEvent:
    row = wm.WarehouseAuditEvent(
        tenant_id=tenant_id,
        content_record_id=content_record_id,
        content_version_id=content_version_id,
        item_copy_id=item_copy_id,
        event_type=event_type[:64],
        actor_user_id=actor_user_id,
        transaction_id=transaction_id or str(__import__("uuid").uuid4()),
        metadata_json=dict(metadata or {}),
    )
    db.add(row)
    return row


def sync_manual(
    db: Session,
    manual_tenant: manual_models.Tenant,
    manual: manual_models.Manual,
    *,
    actor_user_id: str | None = None,
    include_revisions: bool = True,
) -> tuple[wm.WarehouseContentRecord, list[wm.WarehouseContentVersion]]:
    tenant_id = str(manual_tenant.amo_id)
    resource_type = str(manual.manual_type or "DOCUMENT").strip().upper().replace(" ", "_")
    record = ensure_content_record(
        db,
        tenant_id=tenant_id,
        resource_type=resource_type,
        canonical_code=manual.code,
        title=manual.title,
        source_entity_type="CONTROLLED_DOCUMENT",
        source_entity_id=manual.id,
        actor_user_id=actor_user_id,
        lifecycle_status=manual.status,
        owner_department=manual.owner_role,
        metadata={"manual_tenant_id": str(manual.tenant_id)},
    )
    ensure_identifier(
        db,
        tenant_id=tenant_id,
        content_record_id=record.id,
        scheme="DOCUMENT_CODE",
        normalized_value=str(manual.code).strip().upper(),
        display_value=str(manual.code).strip(),
        source="CONTROLLED_DOCUMENT",
    )

    versions: list[wm.WarehouseContentVersion] = []
    if not include_revisions:
        return record, versions

    revisions = (
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.manual_id == manual.id)
        .order_by(manual_models.ManualRevision.created_at.asc(), manual_models.ManualRevision.id.asc())
        .all()
    )
    for revision in revisions:
        status = _enum_value(revision.status_enum) or "DRAFT"
        version = ensure_content_version(
            db,
            tenant_id=tenant_id,
            content_record_id=record.id,
            version_label=str(revision.rev_number),
            source_version_type="MANUAL_REVISION",
            source_version_id=revision.id,
            actor_user_id=str(revision.created_by or actor_user_id or "") or None,
            lifecycle_status=status,
            file_hash=revision.source_sha256,
            effective_at=revision.effective_date,
            change_summary=revision.notes,
            immutable=bool(revision.immutable_locked),
            metadata={
                "issue_number": revision.issue_number,
                "published_at": revision.published_at.isoformat() if revision.published_at else None,
                "source_type": _enum_value(revision.source_type_enum) or None,
                "page_count": revision.source_page_count,
                "is_current": str(manual.current_published_rev_id or "") == str(revision.id),
            },
        )
        versions.append(version)
        if revision.source_sha256 and revision.source_storage_path and revision.source_filename:
            ensure_binary_object(
                db,
                tenant_id=tenant_id,
                content_version_id=version.id,
                filename=revision.source_filename,
                mime_type=revision.source_mime_type or "application/octet-stream",
                sha256=revision.source_sha256,
                storage_uri=revision.source_storage_path,
                metadata={"source": "manual_revision"},
            )
        if revision.manual_uuid:
            ensure_identifier(
                db,
                tenant_id=tenant_id,
                content_record_id=record.id,
                scheme="MANUAL_UUID",
                normalized_value=str(revision.manual_uuid).strip().lower(),
                display_value=str(revision.manual_uuid).strip(),
                source="CONTROLLED_DOCUMENT",
            )
    return record, versions


def sync_library_catalog_item(
    db: Session,
    *,
    tenant_id: str,
    item: lm.LibraryCatalogItem,
    actor_user_id: str | None = None,
) -> tuple[wm.WarehouseContentRecord, wm.WarehouseContentVersion]:
    record = ensure_content_record(
        db,
        tenant_id=tenant_id,
        resource_type="LIBRARY_ITEM",
        canonical_code=item.catalogue_code,
        title=item.title,
        description=item.description,
        source_entity_type="LIBRARY_CATALOG_ITEM",
        source_entity_id=item.id,
        actor_user_id=actor_user_id,
        classification="RESTRICTED" if item.restricted_flag else "INTERNAL",
        lifecycle_status=item.status,
        metadata={
            "material_type": item.material_type,
            "subtitle": item.subtitle,
            "authors": list(item.authors_json or []),
            "publisher": item.publisher,
            "publication_year": item.publication_year,
            "edition": item.edition,
            "language": item.language,
            "subjects": list(item.subjects_json or []),
            "source_provider": item.source_provider,
            "source_url": item.source_url,
            "cover_url": item.cover_url,
            "circulation_policy": dict(item.circulation_policy_json or {}),
        },
    )
    version_label = item.edition or (str(item.publication_year) if item.publication_year else "CATALOGUE")
    version = ensure_content_version(
        db,
        tenant_id=tenant_id,
        content_record_id=record.id,
        version_label=version_label,
        source_version_type="LIBRARY_CATALOG_ITEM",
        source_version_id=item.id,
        actor_user_id=actor_user_id,
        lifecycle_status=item.status,
        immutable=True,
        metadata={"catalogue_snapshot": True},
    )
    identifiers = (
        db.query(lm.LibraryCatalogIdentifier)
        .filter(
            lm.LibraryCatalogIdentifier.tenant_id == tenant_id,
            lm.LibraryCatalogIdentifier.catalog_item_id == item.id,
        )
        .all()
    )
    for identifier in identifiers:
        ensure_identifier(
            db,
            tenant_id=tenant_id,
            content_record_id=record.id,
            scheme=identifier.scheme.upper(),
            normalized_value=identifier.normalized_value,
            display_value=identifier.display_value,
            source=identifier.source,
        )
    return record, version


def _copy_revision_compliance(installed: str | None, required: str | None) -> str:
    if not installed or not required:
        return "NOT_APPLICABLE"
    return "CURRENT" if installed.strip() == required.strip() else "REVISION_REQUIRED"


def sync_library_holding(
    db: Session,
    *,
    tenant_id: str,
    item: lm.LibraryCatalogItem,
    holding: lm.LibraryHolding,
    actor_user_id: str | None = None,
) -> wm.WarehouseItemCopy:
    record, version = sync_library_catalog_item(
        db,
        tenant_id=tenant_id,
        item=item,
        actor_user_id=actor_user_id,
    )
    home = ensure_location(db, tenant_id=tenant_id, path_text=holding.home_location, location_type="LIBRARY")
    current = ensure_location(db, tenant_id=tenant_id, path_text=holding.current_location, location_type="LIBRARY")
    row = (
        db.query(wm.WarehouseItemCopy)
        .filter(
            wm.WarehouseItemCopy.tenant_id == tenant_id,
            wm.WarehouseItemCopy.source_entity_type == "LIBRARY_HOLDING",
            wm.WarehouseItemCopy.source_entity_id == holding.id,
        )
        .first()
    )
    if row is None:
        row = wm.WarehouseItemCopy(
            tenant_id=tenant_id,
            content_record_id=record.id,
            content_version_id=version.id,
            source_entity_type="LIBRARY_HOLDING",
            source_entity_id=holding.id,
            barcode=holding.barcode,
            qr_token=holding.qr_token,
            created_by_user_id=actor_user_id,
        )
        db.add(row)
        db.flush()
    row.copy_number = holding.accession_number or holding.call_number
    row.barcode = holding.barcode
    row.qr_token = holding.qr_token
    row.format = holding.format
    row.status = holding.status
    row.home_location_id = home.id if home else None
    row.current_location_id = current.id if current else None
    row.location_text = holding.current_location
    row.custodian_user_id = holding.holder_user_id
    row.last_inventory_at = holding.last_inventory_at
    row.metadata_json = {
        **dict(row.metadata_json or {}),
        "accession_number": holding.accession_number,
        "call_number": holding.call_number,
        "due_at": holding.due_at.isoformat() if holding.due_at else None,
        "renewal_count": holding.renewal_count,
    }
    return row


def sync_retained_record(
    db: Session,
    *,
    tenant_id: str,
    record_asset: rm.TenantRecordAsset,
    series: rm.TenantRecordSeries,
    actor_user_id: str | None = None,
) -> tuple[wm.WarehouseContentRecord, wm.WarehouseContentVersion]:
    record = ensure_content_record(
        db,
        tenant_id=tenant_id,
        resource_type="RETAINED_RECORD",
        canonical_code=record_asset.record_number,
        title=record_asset.title,
        source_entity_type="RETAINED_RECORD",
        source_entity_id=record_asset.id,
        actor_user_id=actor_user_id,
        classification="RESTRICTED" if series.restricted_flag else "INTERNAL",
        lifecycle_status=record_asset.disposition_status,
        owner_department=series.owner_department,
        metadata={
            "series_id": series.id,
            "series_code": series.code,
            "source_module": record_asset.source_module,
            "source_entity_type": record_asset.source_entity_type,
            "source_entity_id": record_asset.source_entity_id,
            "retention_due_at": record_asset.retention_due_at.isoformat() if record_asset.retention_due_at else None,
            "legal_hold": bool(record_asset.legal_hold),
            "access_scope": dict(record_asset.access_scope_json or {}),
        },
    )
    version = ensure_content_version(
        db,
        tenant_id=tenant_id,
        content_record_id=record.id,
        version_label="CAPTURED",
        source_version_type="RETAINED_RECORD",
        source_version_id=record_asset.id,
        actor_user_id=actor_user_id,
        lifecycle_status=record_asset.disposition_status,
        file_hash=record_asset.sha256,
        effective_at=record_asset.captured_at,
        immutable=True,
        metadata={"record_series_code": series.code},
    )
    if record_asset.sha256 and record_asset.storage_path:
        ensure_binary_object(
            db,
            tenant_id=tenant_id,
            content_version_id=version.id,
            filename=record_asset.filename,
            mime_type=record_asset.mime_type,
            sha256=record_asset.sha256,
            storage_uri=record_asset.storage_path,
            size_bytes=record_asset.size_bytes,
            metadata={"source": "records_vault"},
        )
    ensure_identifier(
        db,
        tenant_id=tenant_id,
        content_record_id=record.id,
        scheme="RECORD_NUMBER",
        normalized_value=record_asset.record_number.strip().upper(),
        display_value=record_asset.record_number,
        source="RECORDS_VAULT",
    )
    return record, version


def sync_controlled_copy(
    db: Session,
    *,
    manual_tenant: manual_models.Tenant,
    copy: dm.DocumentControlledCopy,
    actor_user_id: str | None = None,
) -> wm.WarehouseItemCopy | None:
    manual = (
        db.query(manual_models.Manual)
        .filter(
            manual_models.Manual.tenant_id == manual_tenant.id,
            manual_models.Manual.id == copy.manual_id,
        )
        .first()
    )
    if manual is None:
        return None
    record, versions = sync_manual(db, manual_tenant, manual, actor_user_id=actor_user_id, include_revisions=True)
    version_map = {row.source_version_id: row for row in versions}
    installed = (
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.id == copy.revision_id)
        .first()
    )
    required = (
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.id == manual.current_published_rev_id)
        .first()
        if manual.current_published_rev_id
        else None
    )
    location = ensure_location(db, tenant_id=str(manual_tenant.amo_id), path_text=copy.location_text, location_type="CONTROLLED_COPY")
    barcode = f"CTRL-{manual.code}-{copy.copy_number}"[:128]
    row = (
        db.query(wm.WarehouseItemCopy)
        .filter(
            wm.WarehouseItemCopy.tenant_id == str(manual_tenant.amo_id),
            wm.WarehouseItemCopy.source_entity_type == "CONTROLLED_COPY",
            wm.WarehouseItemCopy.source_entity_id == copy.id,
        )
        .first()
    )
    if row is None:
        row = wm.WarehouseItemCopy(
            tenant_id=str(manual_tenant.amo_id),
            content_record_id=record.id,
            source_entity_type="CONTROLLED_COPY",
            source_entity_id=copy.id,
            barcode=barcode,
            qr_token=f"CONTROLLED-{copy.id}",
            created_by_user_id=actor_user_id,
        )
        db.add(row)
        db.flush()
    row.content_version_id = version_map.get(str(copy.revision_id)).id if str(copy.revision_id) in version_map else None
    row.copy_number = copy.copy_number
    row.format = copy.format
    row.status = copy.status
    row.home_location_id = location.id if location else None
    row.current_location_id = location.id if location else None
    row.location_text = copy.location_text
    row.custodian_user_id = copy.holder_user_id
    row.installed_version_label = installed.rev_number if installed else None
    row.required_version_label = required.rev_number if required else None
    row.revision_compliance = _copy_revision_compliance(row.installed_version_label, row.required_version_label)
    row.metadata_json = {
        **dict(row.metadata_json or {}),
        "holder_name": copy.holder_name,
        "due_back_at": copy.due_back_at.isoformat() if copy.due_back_at else None,
    }
    return row



def _warehouse_record_for_manual(
    db: Session,
    *,
    tenant_id: str,
    manual_id: str,
) -> wm.WarehouseContentRecord | None:
    return (
        db.query(wm.WarehouseContentRecord)
        .filter(
            wm.WarehouseContentRecord.tenant_id == tenant_id,
            wm.WarehouseContentRecord.source_entity_type == "CONTROLLED_DOCUMENT",
            wm.WarehouseContentRecord.source_entity_id == str(manual_id),
        )
        .first()
    )


def _warehouse_version_for_manual_revision(
    db: Session,
    *,
    tenant_id: str,
    revision_id: str | None,
) -> wm.WarehouseContentVersion | None:
    if not revision_id:
        return None
    return (
        db.query(wm.WarehouseContentVersion)
        .filter(
            wm.WarehouseContentVersion.tenant_id == tenant_id,
            wm.WarehouseContentVersion.source_version_type == "MANUAL_REVISION",
            wm.WarehouseContentVersion.source_version_id == str(revision_id),
        )
        .first()
    )


def sync_governed_relationships(
    db: Session,
    *,
    manual_tenant: manual_models.Tenant,
    actor_user_id: str | None = None,
) -> int:
    """Project existing document governance links into the cross-resource graph."""
    tenant_id = str(manual_tenant.amo_id)
    relationships = (
        db.query(gm.DocumentGovernedRelationship)
        .filter(
            gm.DocumentGovernedRelationship.tenant_id == tenant_id,
            gm.DocumentGovernedRelationship.resolution_status != "SUPERSEDED",
        )
        .all()
    )
    count = 0
    namespace = uuid.UUID("d3851f76-9f78-4cc8-a98f-c7d891d4f5cc")
    for source in relationships:
        source_record = _warehouse_record_for_manual(
            db,
            tenant_id=tenant_id,
            manual_id=source.source_manual_id,
        )
        if source_record is None:
            continue
        source_version = _warehouse_version_for_manual_revision(
            db,
            tenant_id=tenant_id,
            revision_id=source.source_revision_id,
        )

        target_record = None
        target_version = None
        if source.target_manual_id:
            target_record = _warehouse_record_for_manual(
                db,
                tenant_id=tenant_id,
                manual_id=source.target_manual_id,
            )
            target_version = _warehouse_version_for_manual_revision(
                db,
                tenant_id=tenant_id,
                revision_id=source.target_revision_id,
            )
        elif source.target_entity_id:
            target_type = str(source.target_entity_type or "RELATED_ENTITY").strip().upper()
            target_record = ensure_content_record(
                db,
                tenant_id=tenant_id,
                resource_type=target_type,
                canonical_code=str(source.exact_token or source.target_entity_id),
                title=str(source.section_label or source.exact_token or f"{target_type} {source.target_entity_id}"),
                source_entity_type=target_type,
                source_entity_id=str(source.target_entity_id),
                actor_user_id=actor_user_id,
                lifecycle_status="REFERENCED",
                metadata={
                    "placeholder_from_relationship": True,
                    "relationship_source": source.relationship_source,
                },
            )
        if target_record is None or target_record.id == source_record.id:
            continue

        relation_id = str(uuid.uuid5(namespace, f"{tenant_id}:{source.id}"))
        row = (
            db.query(wm.WarehouseRelationship)
            .filter(wm.WarehouseRelationship.id == relation_id)
            .first()
        )
        if row is None:
            row = wm.WarehouseRelationship(
                id=relation_id,
                tenant_id=tenant_id,
                source_record_id=source_record.id,
                source_version_id=source_version.id if source_version else None,
                relationship_type=str(source.relationship_type).strip().upper(),
                target_record_id=target_record.id,
                target_version_id=target_version.id if target_version else None,
                status="ACTIVE",
                verified_by_user_id=source.confirmed_by_user_id,
                metadata_json={
                    "source_relationship_id": source.id,
                    "relationship_source": source.relationship_source,
                    "occurrence_key": source.occurrence_key,
                    "exact_token": source.exact_token,
                    "exact_quote": source.exact_quote,
                    "page_number": source.page_number,
                    "section_label": source.section_label,
                    "confidence_percent": source.confidence_percent,
                    "resolution_status": source.resolution_status,
                    "provenance": dict(source.provenance_json or {}),
                },
                created_by_user_id=source.created_by_user_id or actor_user_id,
            )
            db.add(row)
        else:
            row.source_version_id = source_version.id if source_version else None
            row.target_version_id = target_version.id if target_version else None
            row.relationship_type = str(source.relationship_type).strip().upper()
            row.status = "ACTIVE"
            row.verified_by_user_id = source.confirmed_by_user_id
            row.metadata_json = {
                **dict(row.metadata_json or {}),
                "confidence_percent": source.confidence_percent,
                "resolution_status": source.resolution_status,
                "provenance": dict(source.provenance_json or {}),
            }
        count += 1
    return count


def sync_manual_acknowledgements(
    db: Session,
    *,
    manual_tenant: manual_models.Tenant,
) -> int:
    """Bind existing reader sign-offs to the exact canonical content version/hash."""
    tenant_id = str(manual_tenant.amo_id)
    rows = (
        db.query(manual_models.Acknowledgement)
        .join(manual_models.ManualRevision, manual_models.ManualRevision.id == manual_models.Acknowledgement.revision_id)
        .join(manual_models.Manual, manual_models.Manual.id == manual_models.ManualRevision.manual_id)
        .filter(
            manual_models.Manual.tenant_id == manual_tenant.id,
            manual_models.Acknowledgement.holder_user_id.isnot(None),
            manual_models.Acknowledgement.acknowledged_at.isnot(None),
        )
        .all()
    )
    count = 0
    for source in rows:
        version = _warehouse_version_for_manual_revision(
            db,
            tenant_id=tenant_id,
            revision_id=source.revision_id,
        )
        if version is None:
            continue
        record = (
            db.query(wm.WarehouseContentRecord)
            .filter(wm.WarehouseContentRecord.id == version.content_record_id)
            .first()
        )
        if record is None:
            continue
        existing = (
            db.query(wm.WarehouseAcknowledgement)
            .filter(
                wm.WarehouseAcknowledgement.tenant_id == tenant_id,
                wm.WarehouseAcknowledgement.content_version_id == version.id,
                wm.WarehouseAcknowledgement.user_id == source.holder_user_id,
            )
            .first()
        )
        if existing is None:
            db.add(wm.WarehouseAcknowledgement(
                tenant_id=tenant_id,
                content_record_id=record.id,
                content_version_id=version.id,
                user_id=source.holder_user_id,
                file_hash=version.file_hash,
                acknowledgement_method="LEGACY_READER_SIGNOFF",
                session_metadata_json={
                    "source_acknowledgement_id": source.id,
                    "acknowledgement_text": source.acknowledgement_text,
                    "evidence_uri": source.evidence_uri,
                },
                acknowledged_at=source.acknowledged_at,
            ))
        count += 1
    return count


def sync_external_document_references(
    db: Session,
    *,
    manual_tenant: manual_models.Tenant,
    actor_user_id: str | None = None,
) -> int:
    tenant_id = str(manual_tenant.amo_id)
    sources = (
        db.query(dm.ExternalDocumentSource)
        .filter(
            dm.ExternalDocumentSource.tenant_id == tenant_id,
            dm.ExternalDocumentSource.access_url.isnot(None),
        )
        .all()
    )
    count = 0
    for source in sources:
        record = _warehouse_record_for_manual(
            db,
            tenant_id=tenant_id,
            manual_id=source.manual_id,
        )
        if record is None or not source.access_url:
            continue
        existing = (
            db.query(wm.WarehouseExternalReference)
            .filter(
                wm.WarehouseExternalReference.tenant_id == tenant_id,
                wm.WarehouseExternalReference.content_record_id == record.id,
                wm.WarehouseExternalReference.provider == str(source.provider).strip().upper(),
                wm.WarehouseExternalReference.url == source.access_url,
            )
            .first()
        )
        if existing is None:
            db.add(wm.WarehouseExternalReference(
                tenant_id=tenant_id,
                content_record_id=record.id,
                provider=str(source.provider).strip().upper(),
                reference_type="AUTHORITATIVE_SOURCE",
                external_id=source.subscription_reference,
                url=source.access_url,
                metadata_json={
                    "authority": source.authority,
                    "status": source.status,
                    "update_method": source.update_method,
                    "last_checked_at": source.last_checked_at.isoformat() if source.last_checked_at else None,
                    "next_check_due_at": source.next_check_due_at.isoformat() if source.next_check_due_at else None,
                },
                created_by_user_id=actor_user_id,
            ))
        count += 1
    return count

def reconcile_tenant_warehouse(
    db: Session,
    *,
    manual_tenant: manual_models.Tenant,
    actor_user_id: str | None = None,
) -> dict[str, int]:
    tenant_id = str(manual_tenant.amo_id)
    counts = {
        "controlled_documents": 0,
        "controlled_versions": 0,
        "controlled_copies": 0,
        "library_items": 0,
        "library_holdings": 0,
        "retained_records": 0,
        "relationships": 0,
        "acknowledgements": 0,
        "external_references": 0,
    }

    manuals = (
        db.query(manual_models.Manual)
        .filter(manual_models.Manual.tenant_id == manual_tenant.id)
        .all()
    )
    for manual in manuals:
        _record, versions = sync_manual(
            db,
            manual_tenant,
            manual,
            actor_user_id=actor_user_id,
            include_revisions=True,
        )
        counts["controlled_documents"] += 1
        counts["controlled_versions"] += len(versions)

    items = db.query(lm.LibraryCatalogItem).filter(lm.LibraryCatalogItem.tenant_id == tenant_id).all()
    for item in items:
        sync_library_catalog_item(db, tenant_id=tenant_id, item=item, actor_user_id=actor_user_id)
        counts["library_items"] += 1

    holdings = (
        db.query(lm.LibraryHolding, lm.LibraryCatalogItem)
        .join(lm.LibraryCatalogItem, lm.LibraryCatalogItem.id == lm.LibraryHolding.catalog_item_id)
        .filter(
            lm.LibraryHolding.tenant_id == tenant_id,
            lm.LibraryCatalogItem.tenant_id == tenant_id,
        )
        .all()
    )
    for holding, item in holdings:
        sync_library_holding(
            db,
            tenant_id=tenant_id,
            item=item,
            holding=holding,
            actor_user_id=actor_user_id,
        )
        counts["library_holdings"] += 1

    records = (
        db.query(rm.TenantRecordAsset, rm.TenantRecordSeries)
        .join(rm.TenantRecordSeries, rm.TenantRecordSeries.id == rm.TenantRecordAsset.series_id)
        .filter(
            rm.TenantRecordAsset.tenant_id == tenant_id,
            rm.TenantRecordSeries.tenant_id == tenant_id,
        )
        .all()
    )
    for record_asset, series in records:
        sync_retained_record(
            db,
            tenant_id=tenant_id,
            record_asset=record_asset,
            series=series,
            actor_user_id=actor_user_id,
        )
        counts["retained_records"] += 1

    copies = db.query(dm.DocumentControlledCopy).filter(dm.DocumentControlledCopy.tenant_id == tenant_id).all()
    for copy in copies:
        if sync_controlled_copy(db, manual_tenant=manual_tenant, copy=copy, actor_user_id=actor_user_id):
            counts["controlled_copies"] += 1

    counts["relationships"] = sync_governed_relationships(
        db,
        manual_tenant=manual_tenant,
        actor_user_id=actor_user_id,
    )
    counts["acknowledgements"] = sync_manual_acknowledgements(
        db,
        manual_tenant=manual_tenant,
    )
    counts["external_references"] = sync_external_document_references(
        db,
        manual_tenant=manual_tenant,
        actor_user_id=actor_user_id,
    )

    db.flush()
    return counts
