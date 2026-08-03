from pathlib import Path
import re


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected one match in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def regex_once(path: Path, pattern: str, replacement: str, *, flags: int = 0) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"Expected one regex match in {path}, found {count}: {pattern}")
    path.write_text(updated, encoding="utf-8")


service = Path("backend/amodb/apps/procurement/document_service.py")
contract = Path("backend/tests/test_procurement_document_contract.py")

replace_once(
    service,
    "from sqlalchemy.orm import Session\n\nfrom . import document_models, models\n",
    "from sqlalchemy.orm import Session\n\nfrom amodb.apps.audit import schemas as audit_schemas\nfrom amodb.apps.audit import services as audit_services\n\nfrom . import document_models, models\n",
)

regex_once(
    service,
    r"def _event\(\n.*?\n\ndef _clean\(",
    '''def _event(
    db: Session,
    *,
    amo_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_user_id: str | None,
    detail: dict,
) -> None:
    db.add(
        models.ProcurementEvent(
            amo_id=amo_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            detail=detail,
        )
    )
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            actor_user_id=actor_user_id,
            after_json=detail,
        ),
    )


def _clean(''',
    flags=re.DOTALL,
)

replace_once(
    service,
    "    record = get_document(db, amo_id=amo_id, document_id=document_id)\n    if record.status != document_models.ProcurementDocumentStatus.ACTIVE:\n",
    '''    record = (
        db.query(document_models.ProcurementDocument)
        .filter(
            document_models.ProcurementDocument.amo_id == amo_id,
            document_models.ProcurementDocument.id == document_id,
        )
        .with_for_update()
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="The Procurement document was not found.")
    if record.status != document_models.ProcurementDocumentStatus.ACTIVE:
''',
)

text = contract.read_text(encoding="utf-8")
if "test_quality_evidence_decision_is_atomic_and_shared_audited" not in text:
    contract.write_text(text + '''


def test_quality_evidence_decision_is_atomic_and_shared_audited():
    service = read("amodb/apps/procurement/document_service.py")
    assert ".with_for_update()" in service
    assert "audit_services.create_audit_event(" in service
    assert "audit_schemas.AuditEventCreate(" in service
    assert "after_json=detail" in service
''', encoding="utf-8")

updated = service.read_text(encoding="utf-8")
for token in [".with_for_update()", "audit_services.create_audit_event(", "audit_schemas.AuditEventCreate("]:
    if token not in updated:
        raise SystemExit(f"Required atomic/audit token missing: {token}")
