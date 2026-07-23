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
        "        from amodb.apps.accounts import models as account_models\n"
        "        from amodb.apps.quality import models as quality_models\n\n"
        "        quality_models.QMSAuditScope.__table__.create(bind=bind, checkfirst=True)\n"
        "        for amo_id, in db.query(account_models.AMO.id).all():\n"
        "            for code, name, party_level, default_kind, sort_order, description in _DEFAULT_AUDIT_SCOPES:\n"
        "                exists = (\n"
        "                    db.query(quality_models.QMSAuditScope.id)\n"
        "                    .filter(\n"
        "                        quality_models.QMSAuditScope.amo_id == amo_id,\n"
        "                        quality_models.QMSAuditScope.code == code,\n"
        "                    )\n"
        "                    .first()\n"
        "                )\n"
        "                if exists:\n"
        "                    continue\n"
        "                db.add(\n"
        "                    quality_models.QMSAuditScope(\n"
        "                        amo_id=amo_id,\n"
        "                        code=code,\n"
        "                        name=name,\n"
        "                        description=description,\n"
        "                        party_level=party_level,\n"
        "                        default_kind=quality_models.QMSAuditKind(default_kind),\n"
        "                        is_active=True,\n"
        "                        is_system_default=True,\n"
        "                        sort_order=sort_order,\n"
        "                    )\n"
        "                )\n"
        "        db.flush()\n"
        "        return True\n\n"
        "    changed = False\n"
        "    inspector = inspect(bind)\n",
    )

    replace_exact(
        "backend/amodb/apps/quality/tests/test_workflow_transitions.py",
        "from starlette.requests import Request\n",
        "import pytest\nfrom fastapi import HTTPException\nfrom starlette.requests import Request\n",
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
        "backend/amodb/apps/quality/tests/test_workflow_transitions.py",
        "    response = quality_router.update_audit(\n"
        "        audit_id=audit.id,\n"
        "        payload=payload,\n"
        "        request=_make_request(),\n"
        "        db=db_session,\n"
        "        current_user=user,\n"
        "    )\n\n"
        "    assert response.status_code == 400\n"
        "    body = json.loads(response.body)\n"
        "    assert body[\"error\"] == \"missing_requirements\"\n"
        "    assert body[\"detail\"][0][\"field\"] == \"findings\"\n",
        "    with pytest.raises(HTTPException) as exc:\n"
        "        quality_router.update_audit(\n"
        "            audit_id=audit.id,\n"
        "            payload=payload,\n"
        "            request=_make_request(),\n"
        "            db=db_session,\n"
        "            current_user=user,\n"
        "        )\n\n"
        "    assert exc.value.status_code == 400\n"
        "    assert \"issued CAR\" in str(exc.value.detail)\n",
    )

    replace_exact(
        "backend/amodb/apps/quality/tests/test_audit_workflow_enforcement.py",
        "        audit_ref=\"AUD-WF-1\",\n        title=\"Workflow Audit\",\n",
        "        audit_ref=\"AUD-WF-1\",\n"
        "        reference_family=\"LEGACY\",\n"
        "        unit_code=\"WF\",\n"
        "        ref_year=date.today().year % 100,\n"
        "        ref_sequence=999,\n"
        "        title=\"Workflow Audit\",\n",
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
        "        status=quality_models.CARStatus.IN_PROGRESS,\n"
        "        invite_token=\"tok1\",\n",
        "        status=quality_models.CARStatus.PENDING_VERIFICATION,\n"
        "        invite_token=\"tok1\",\n",
    )
    replace_exact(
        "backend/amodb/apps/quality/tests/test_audit_workflow_enforcement.py",
        "        quality_router.submit_car_from_invite(invite_token=\"tok2\", payload=payload, db=db_session)\n",
        "        quality_router.submit_car_from_invite(\n"
        "            invite_token=\"tok2\",\n"
        "            payload=payload,\n"
        "            request=_req(),\n"
        "            db=db_session,\n"
        "        )\n",
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
        "    rev = quality_models.QMSDocumentRevision(\n"
        "        document_id=doc.id,\n",
        "    rev = quality_models.QMSDocumentRevision(\n"
        "        amo_id=amo.id,\n"
        "        document_id=doc.id,\n",
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
        "    rev = quality_models.QMSDocumentRevision(\n"
        "        document_id=doc.id,\n",
        "    rev = quality_models.QMSDocumentRevision(\n"
        "        amo_id=amo.id,\n"
        "        document_id=doc.id,\n",
    )
    replace_exact(
        "backend/amodb/apps/quality/tests/test_task_integrations.py",
        "    dist = quality_models.QMSDocumentDistribution(\n"
        "        document_id=doc.id,\n",
        "    dist = quality_models.QMSDocumentDistribution(\n"
        "        amo_id=amo.id,\n"
        "        document_id=doc.id,\n",
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
