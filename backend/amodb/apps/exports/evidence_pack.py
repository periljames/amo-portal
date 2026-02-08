from __future__ import annotations

import enum
import io
import json
import os
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional
from uuid import UUID

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from ..accounts import models as account_models
from ..audit import services as audit_services

MAX_EVIDENCE_PACK_BYTES = int(os.getenv("EVIDENCE_PACK_MAX_BYTES", str(50 * 1024 * 1024)))
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _to_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, default=_serialize_value, sort_keys=True, indent=2).encode("utf-8")


def _model_to_dict(obj: Any) -> dict:
    mapper = inspect(obj).mapper
    data: dict[str, Any] = {}
    for column in mapper.column_attrs:
        key = column.key
        data[key] = _serialize_value(getattr(obj, key))
    return data


def _event_to_dict(event: Any) -> dict:
    if isinstance(event, dict):
        return {key: _serialize_value(value) for key, value in event.items()}
    return _model_to_dict(event)


def _extract_event_timestamp(event: dict) -> str:
    for key in ("occurred_at", "created_at"):
        value = event.get(key)
        if value:
            return str(value)
    return ""


def _sorted_events(events: Iterable[Any]) -> list[dict]:
    normalized = [_event_to_dict(event) for event in events]
    return sorted(normalized, key=_extract_event_timestamp)


def _write_zip(entries: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    buffer.seek(0)
    return buffer.read()


def _add_entry(entries: list[tuple[str, bytes]], name: str, payload: Any) -> int:
    data = _to_json_bytes(payload)
    entries.append((name, data))
    return len(data)


def _load_attachment(
    entries: list[tuple[str, bytes]],
    *,
    name: str,
    path: Path,
    current_size: int,
    max_size: int,
    omitted: list[dict[str, Any]],
) -> int:
    if not path.exists():
        omitted.append({"path": name, "reason": "missing"})
        return 0
    size = path.stat().st_size
    if max_size and current_size + size > max_size:
        omitted.append({"path": name, "reason": "exceeds_limit", "size_bytes": size})
        return 0
    data = path.read_bytes()
    entries.append((name, data))
    return len(data)


def _collect_timeline(db: Session, *, amo_id: str, entities: Iterable[tuple[str, str]]) -> list[dict]:
    events: list[dict] = []
    for entity_type, entity_id in entities:
        result = audit_services.list_audit_events(
            db,
            amo_id=amo_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        events.extend(_event_to_dict(item) for item in result)
    return _sorted_events(events)


def _build_audit_pack(
    db: Session,
    *,
    audit_id: UUID,
    amo_id: str,
) -> tuple[dict, dict[str, Any], list[dict], list[tuple[str, Path]]]:
    from ..quality import models as quality_models

    audit = db.query(quality_models.QMSAudit).filter(quality_models.QMSAudit.id == audit_id).first()
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")

    findings = (
        db.query(quality_models.QMSAuditFinding)
        .filter(quality_models.QMSAuditFinding.audit_id == audit.id)
        .order_by(quality_models.QMSAuditFinding.created_at.asc())
        .all()
    )
    caps = [finding.cap for finding in findings if finding.cap]

    cars: list[quality_models.CorrectiveActionRequest] = []
    if findings:
        cars = (
            db.query(quality_models.CorrectiveActionRequest)
            .filter(quality_models.CorrectiveActionRequest.finding_id.in_([f.id for f in findings]))
            .order_by(quality_models.CorrectiveActionRequest.created_at.asc())
            .all()
        )

    summary = _model_to_dict(audit)
    linked = {
        "findings": [_model_to_dict(finding) for finding in findings],
        "caps": [_model_to_dict(cap) for cap in caps],
        "cars": [_model_to_dict(car) for car in cars],
    }

    entities = [("qms_audit", str(audit.id))]
    entities.extend(("qms_finding", str(finding.id)) for finding in findings)
    entities.extend(("qms_cap", str(cap.id)) for cap in caps)
    entities.extend(("qms_car", str(car.id)) for car in cars)

    timeline = _collect_timeline(db, amo_id=amo_id, entities=entities)

    attachments: list[tuple[str, Path]] = []
    if audit.report_file_ref:
        attachments.append((f"audit_report_{audit.id}.pdf", Path(audit.report_file_ref)))

    return summary, linked, timeline, attachments


def _build_car_pack(
    db: Session,
    *,
    car_id: UUID,
    amo_id: str,
) -> tuple[dict, dict[str, Any], list[dict], list[tuple[str, Path]], Optional[Path], list[dict[str, Any]]]:
    from ..quality import models as quality_models
    from ..quality import service as quality_service

    car = db.query(quality_models.CorrectiveActionRequest).filter(quality_models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CAR not found")

    actions = (
        db.query(quality_models.CARActionLog)
        .filter(quality_models.CARActionLog.car_id == car.id)
        .order_by(quality_models.CARActionLog.created_at.asc())
        .all()
    )
    responses = (
        db.query(quality_models.CARResponse)
        .filter(quality_models.CARResponse.car_id == car.id)
        .order_by(quality_models.CARResponse.submitted_at.asc())
        .all()
    )
    attachments = (
        db.query(quality_models.CARAttachment)
        .filter(quality_models.CARAttachment.car_id == car.id)
        .order_by(quality_models.CARAttachment.uploaded_at.asc())
        .all()
    )

    summary = _model_to_dict(car)
    linked = {
        "actions": [_model_to_dict(action) for action in actions],
        "responses": [_model_to_dict(response) for response in responses],
        "attachments": [_model_to_dict(attachment) for attachment in attachments],
    }

    timeline = _collect_timeline(db, amo_id=amo_id, entities=[("qms_car", str(car.id))])

    attachment_files = [
        (f"{attachment.id}_{attachment.filename}", Path(attachment.file_ref))
        for attachment in attachments
    ]

    omitted: list[dict[str, Any]] = []
    pdf_path: Optional[Path] = None
    try:
        invite_url = quality_service.build_car_invite_link(car)
        pdf_path = quality_service.generate_car_form_pdf(car, invite_url)
    except Exception as exc:
        omitted.append({"path": "car.pdf", "reason": f"pdf_generation_failed: {exc}"})

    return summary, linked, timeline, attachment_files, pdf_path, omitted


def _build_fracas_pack(
    db: Session,
    *,
    case_id: int,
    amo_id: str,
) -> tuple[dict, dict[str, Any], list[dict], list[tuple[str, Path]]]:
    from ..reliability import models as reliability_models

    case = (
        db.query(reliability_models.FRACASCase)
        .filter(reliability_models.FRACASCase.amo_id == amo_id, reliability_models.FRACASCase.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FRACAS case not found")

    actions = (
        db.query(reliability_models.FRACASAction)
        .filter(reliability_models.FRACASAction.fracas_case_id == case.id)
        .order_by(reliability_models.FRACASAction.created_at.asc())
        .all()
    )

    summary = _model_to_dict(case)
    linked = {
        "actions": [_model_to_dict(action) for action in actions],
    }

    entities = [("fracas_case", str(case.id))]
    entities.extend(("fracas_action", str(action.id)) for action in actions)
    timeline = _collect_timeline(db, amo_id=amo_id, entities=entities)

    return summary, linked, timeline, []


def _build_training_user_pack(
    db: Session,
    *,
    user_id: str,
    amo_id: str,
) -> tuple[dict, dict[str, Any], list[dict], list[tuple[str, Path]]]:
    from ..training import models as training_models

    user = (
        db.query(account_models.User)
        .filter(account_models.User.id == user_id, account_models.User.amo_id == amo_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training user not found")

    records = (
        db.query(training_models.TrainingRecord)
        .filter(training_models.TrainingRecord.amo_id == amo_id, training_models.TrainingRecord.user_id == user_id)
        .order_by(training_models.TrainingRecord.completion_date.desc())
        .all()
    )
    deferrals = (
        db.query(training_models.TrainingDeferralRequest)
        .filter(training_models.TrainingDeferralRequest.amo_id == amo_id, training_models.TrainingDeferralRequest.user_id == user_id)
        .order_by(training_models.TrainingDeferralRequest.requested_at.desc())
        .all()
    )
    files = (
        db.query(training_models.TrainingFile)
        .filter(training_models.TrainingFile.amo_id == amo_id, training_models.TrainingFile.owner_user_id == user_id)
        .order_by(training_models.TrainingFile.created_at.desc())
        .all()
    )

    summary = {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "staff_code": user.staff_code,
        "department_id": user.department_id,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
    }
    linked = {
        "records": [_model_to_dict(record) for record in records],
        "deferrals": [_model_to_dict(deferral) for deferral in deferrals],
        "files": [_model_to_dict(file) for file in files],
    }

    entities = [("training_user", user.id)]
    entities.extend(("TrainingRecord", record.id) for record in records)
    entities.extend(("TrainingFile", file.id) for file in files)
    entities.extend(("TrainingDeferralRequest", deferral.id) for deferral in deferrals)
    timeline = _collect_timeline(db, amo_id=amo_id, entities=entities)

    attachment_files = [
        (f"{file.id}_{file.original_filename}", Path(file.storage_path))
        for file in files
    ]

    return summary, linked, timeline, attachment_files


def build_evidence_pack(
    entity_type: str,
    entity_id: str | UUID | int,
    db: Session,
    *,
    actor_user_id: Optional[str],
    correlation_id: Optional[str],
    amo_id: str,
) -> StreamingResponse:
    entries: list[tuple[str, bytes]] = []
    omitted_files: list[dict[str, Any]] = []
    current_size = 0

    if entity_type == "qms_audit":
        summary, linked, timeline, attachment_files = _build_audit_pack(
            db,
            audit_id=UUID(str(entity_id)),
            amo_id=amo_id,
        )
        current_size += _add_entry(entries, "summary.json", summary)
        current_size += _add_entry(entries, "linked/findings.json", linked["findings"])
        current_size += _add_entry(entries, "linked/caps.json", linked["caps"])
        current_size += _add_entry(entries, "linked/cars.json", linked["cars"])
        current_size += _add_entry(entries, "timeline.json", timeline)
        for name, path in attachment_files:
            current_size += _load_attachment(
                entries,
                name=f"attachments/{name}",
                path=path,
                current_size=current_size,
                max_size=MAX_EVIDENCE_PACK_BYTES,
                omitted=omitted_files,
            )

    elif entity_type == "qms_car":
        summary, linked, timeline, attachment_files, pdf_path, pdf_omitted = _build_car_pack(
            db,
            car_id=UUID(str(entity_id)),
            amo_id=amo_id,
        )
        omitted_files.extend(pdf_omitted)
        current_size += _add_entry(entries, "summary.json", summary)
        current_size += _add_entry(entries, "linked/actions.json", linked["actions"])
        current_size += _add_entry(entries, "linked/responses.json", linked["responses"])
        current_size += _add_entry(entries, "linked/attachments.json", linked["attachments"])
        current_size += _add_entry(entries, "timeline.json", timeline)
        for name, path in attachment_files:
            current_size += _load_attachment(
                entries,
                name=f"attachments/{name}",
                path=path,
                current_size=current_size,
                max_size=MAX_EVIDENCE_PACK_BYTES,
                omitted=omitted_files,
            )
        if pdf_path is not None:
            current_size += _load_attachment(
                entries,
                name="car.pdf",
                path=pdf_path,
                current_size=current_size,
                max_size=MAX_EVIDENCE_PACK_BYTES,
                omitted=omitted_files,
            )

    elif entity_type == "fracas_case":
        summary, linked, timeline, attachment_files = _build_fracas_pack(
            db,
            case_id=int(entity_id),
            amo_id=amo_id,
        )
        current_size += _add_entry(entries, "summary.json", summary)
        current_size += _add_entry(entries, "linked/actions.json", linked["actions"])
        current_size += _add_entry(entries, "timeline.json", timeline)
        for name, path in attachment_files:
            current_size += _load_attachment(
                entries,
                name=f"attachments/{name}",
                path=path,
                current_size=current_size,
                max_size=MAX_EVIDENCE_PACK_BYTES,
                omitted=omitted_files,
            )

    elif entity_type == "training_user":
        summary, linked, timeline, attachment_files = _build_training_user_pack(
            db,
            user_id=str(entity_id),
            amo_id=amo_id,
        )
        current_size += _add_entry(entries, "summary.json", summary)
        current_size += _add_entry(entries, "linked/records.json", linked["records"])
        current_size += _add_entry(entries, "linked/deferrals.json", linked["deferrals"])
        current_size += _add_entry(entries, "linked/files.json", linked["files"])
        current_size += _add_entry(entries, "timeline.json", timeline)
        for name, path in attachment_files:
            current_size += _load_attachment(
                entries,
                name=f"attachments/{name}",
                path=path,
                current_size=current_size,
                max_size=MAX_EVIDENCE_PACK_BYTES,
                omitted=omitted_files,
            )

    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported evidence pack type")

    if omitted_files:
        current_size += _add_entry(
            entries,
            "manifest.json",
            {
                "limit_bytes": MAX_EVIDENCE_PACK_BYTES,
                "total_bytes": current_size,
                "omitted": omitted_files,
            },
        )

    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=str(entity_id),
        action="export_evidence_pack",
        correlation_id=correlation_id,
        metadata={"module": "exports"},
        critical=True,
    )
    db.commit()

    zip_bytes = _write_zip(entries)
    filename = f"{entity_type}_{entity_id}_evidence_pack.zip"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}

    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers=headers,
    )
