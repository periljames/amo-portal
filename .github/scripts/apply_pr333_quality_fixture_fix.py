from __future__ import annotations

from pathlib import Path


def replace_exact(path: str, old: str, new: str, expected: int = 1) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != expected:
        raise SystemExit(
            f"{path}: expected {expected} occurrences, found {actual}: {old!r}"
        )
    file_path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    replace_exact(
        "backend/amodb/apps/quality/schema_compat.py",
        "    changed = False\n    inspector = inspect(db.get_bind())\n",
        "    bind = db.get_bind()\n"
        "    if getattr(bind.dialect, \"name\", \"\") != \"postgresql\":\n"
        "        return False\n\n"
        "    changed = False\n"
        "    inspector = inspect(bind)\n",
    )

    replace_exact(
        "backend/amodb/apps/quality/tests/test_workflow_transitions.py",
        "    finding = quality_models.QMSAuditFinding(\n        audit_id=audit.id,\n",
        "    finding = quality_models.QMSAuditFinding(\n"
        "        amo_id=amo.id,\n"
        "        audit_id=audit.id,\n",
        expected=4,
    )
    replace_exact(
        "backend/amodb/apps/quality/tests/test_workflow_transitions.py",
        "    cap = quality_models.QMSCorrectiveAction(\n        finding_id=finding.id,\n",
        "    cap = quality_models.QMSCorrectiveAction(\n"
        "        amo_id=amo.id,\n"
        "        finding_id=finding.id,\n",
    )

    replace_exact(
        "backend/amodb/apps/quality/tests/test_audit_workflow_enforcement.py",
        "    _, quality, _, audit = _seed_audit(db_session)\n",
        "    amo, quality, _, audit = _seed_audit(db_session)\n",
        expected=2,
    )
    replace_exact(
        "backend/amodb/apps/quality/tests/test_audit_workflow_enforcement.py",
        "    _, _, _, audit = _seed_audit(db_session)\n",
        "    amo, _, _, audit = _seed_audit(db_session)\n",
    )
    replace_exact(
        "backend/amodb/apps/quality/tests/test_audit_workflow_enforcement.py",
        "    finding = quality_models.QMSAuditFinding(\n        audit_id=audit.id,\n",
        "    finding = quality_models.QMSAuditFinding(\n"
        "        amo_id=amo.id,\n"
        "        audit_id=audit.id,\n",
        expected=3,
    )
    replace_exact(
        "backend/amodb/apps/quality/tests/test_audit_workflow_enforcement.py",
        "    car = quality_models.CorrectiveActionRequest(\n"
        "        program=quality_models.CARProgram.QUALITY,\n",
        "    car = quality_models.CorrectiveActionRequest(\n"
        "        amo_id=amo.id,\n"
        "        program=quality_models.CARProgram.QUALITY,\n",
        expected=2,
    )
    replace_exact(
        "backend/amodb/apps/quality/tests/test_audit_workflow_enforcement.py",
        "    schedule = quality_models.QMSAuditSchedule(\n"
        "        domain=quality_models.QMSDomain.AMO,\n",
        "    schedule = quality_models.QMSAuditSchedule(\n"
        "        amo_id=amo.id,\n"
        "        domain=quality_models.QMSDomain.AMO,\n",
    )

    replace_exact(
        "backend/amodb/apps/quality/tests/test_audit_events.py",
        "    doc = quality_models.QMSDocument(\n"
        "        domain=quality_models.QMSDomain.AMO,\n",
        "    doc = quality_models.QMSDocument(\n"
        "        amo_id=amo.id,\n"
        "        domain=quality_models.QMSDomain.AMO,\n",
    )
    replace_exact(
        "backend/amodb/apps/quality/tests/test_audit_events.py",
        "    finding = quality_models.QMSAuditFinding(\n        audit_id=audit.id,\n",
        "    finding = quality_models.QMSAuditFinding(\n"
        "        amo_id=amo.id,\n"
        "        audit_id=audit.id,\n",
    )
    replace_exact(
        "backend/amodb/apps/quality/tests/test_audit_events.py",
        "    car = quality_service.create_car(\n"
        "        db_session,\n"
        "        program=quality_models.CARProgram.QUALITY,\n",
        "    car = quality_service.create_car(\n"
        "        db_session,\n"
        "        amo_id=amo.id,\n"
        "        program=quality_models.CARProgram.QUALITY,\n",
    )

    replace_exact(
        "backend/amodb/apps/quality/tests/test_task_integrations.py",
        "    doc = quality_models.QMSDocument(\n"
        "        domain=quality_models.QMSDomain.AMO,\n",
        "    doc = quality_models.QMSDocument(\n"
        "        amo_id=amo.id,\n"
        "        domain=quality_models.QMSDomain.AMO,\n",
    )
    replace_exact(
        "backend/amodb/apps/quality/tests/test_task_integrations.py",
        "    finding = quality_models.QMSAuditFinding(\n        audit_id=audit.id,\n",
        "    finding = quality_models.QMSAuditFinding(\n"
        "        amo_id=amo.id,\n"
        "        audit_id=audit.id,\n",
    )

    replace_exact(
        "backend/amodb/apps/quality/tests/test_evidence_pack_exports.py",
        "    car = quality_service.create_car(\n"
        "        db_session,\n"
        "        program=quality_models.CARProgram.QUALITY,\n",
        "    car = quality_service.create_car(\n"
        "        db_session,\n"
        "        amo_id=amo.id,\n"
        "        program=quality_models.CARProgram.QUALITY,\n",
    )


if __name__ == "__main__":
    main()
