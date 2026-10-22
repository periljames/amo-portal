import json
from datetime import datetime, timezone

from starlette.routing import Match
from amodb.apps.accounts.models import AMO
from amodb.apps.quality import assurance_evidence_register as vault
from amodb.apps.quality.audit_evidence_models import QualityAuditEvidenceArtifact
from amodb.apps.quality.models import CARAttachment, QMSFindingAttachment
from amodb.apps.quality.people_authorization_models import QualityAuthorizationEvidence
from amodb.apps.quality.tests.test_register_pagination import _finding, _car
from amodb.apps.quality.tests.test_assurance_workspace_workflows import authorization_context
from amodb.apps.quality import people_authorization_router as people


def test_evidence_search_owns_the_live_route():
    from amodb.apps.quality.canonical_router import router
    scope = {"type":"http", "method":"GET", "path":"/api/maintenance/test/quality/evidence-vault/search", "root_path":""}
    matched = next(route for route in router.routes if route.matches(scope)[0] == Match.FULL)
    assert matched.endpoint is vault.evidence_files


def test_vault_indexes_retained_evidence_with_tenant_search_and_paging(db_session, authorization_context):
    ctx, subject, rule = authorization_context
    for model in [QualityAuditEvidenceArtifact, QMSFindingAttachment]:
        model.__table__.create(db_session.get_bind(), checkfirst=True)
    finding = _finding(db_session, amo_id=ctx.amo_id)
    car = _car(db_session, amo_id=ctx.amo_id, requested_by_user_id=ctx.user_id, finding_id=finding.id, title="Evidence source")
    case = people.create_authorization_case(people.AuthorizationCaseCreate(user_id=subject.id, requested_rule_id=rule.id, nomination_reason="Index isolated authorization evidence"), ctx=ctx, db=db_session)["case"]
    db_session.add_all([
        QualityAuditEvidenceArtifact(amo_id=ctx.amo_id, audit_id=finding.audit_id, source_type="INTERNAL_USER", filename="own-audit.pdf", file_ref="PRIVATE-AUDIT-PATH", size_bytes=123, sha256="a"*64),
        QMSFindingAttachment(finding_id=finding.id, filename="own-finding.pdf", file_ref="PRIVATE-FINDING-PATH", size_bytes=321, sha256="b"*64),
        CARAttachment(car_id=car.id, filename="own-car.pdf", file_ref="PRIVATE-CAR-PATH", size_bytes=456, sha256="c"*64),
        QualityAuthorizationEvidence(amo_id=ctx.amo_id, case_id=case["id"], evidence_type="OTHER", label="Retained case file", original_filename="own-authorization.pdf", storage_path="PRIVATE-AUTHORIZATION-PATH", size_bytes=789, sha256="d"*64),
    ])
    other = AMO(amo_code="OTHER", name="Other tenant", login_slug="other-evidence")
    db_session.add(other); db_session.commit()
    foreign = _finding(db_session, amo_id=other.id)
    db_session.add(QualityAuditEvidenceArtifact(amo_id=other.id, audit_id=foreign.audit_id, source_type="INTERNAL_USER", filename="own-foreign.pdf", file_ref="PRIVATE-FOREIGN-PATH", size_bytes=1, sha256="e"*64))
    db_session.commit()
    result = vault.read_evidence_register(db_session, ctx)
    assert result["total"] == 4
    assert {row["filename"] for row in result["items"]} == {"own-audit.pdf", "own-finding.pdf", "own-car.pdf", "own-authorization.pdf"}
    assert "PRIVATE-" not in json.dumps(result, default=str)
    assert all(row["download_url"].startswith("/api/") for row in result["items"])
    assert next(row for row in result["items"] if row["source"] == "Authorization evidence")["source_route"].endswith("case=" + case["id"])
    first = vault.read_evidence_register(db_session, ctx, q="own", limit=2, offset=0)
    last = vault.read_evidence_register(db_session, ctx, q="own", limit=2, offset=2)
    assert first["total"] == last["total"] == 4
    assert first["has_more"] and not last["has_more"]
    assert {row["id"] for row in first["items"]}.isdisjoint({row["id"] for row in last["items"]})
    assert vault.read_evidence_register(db_session, ctx, q="own-car")["total"] == 1


def test_vault_respects_source_permissions_and_personal_authorization_scope(db_session, authorization_context, monkeypatch):
    ctx, subject, rule = authorization_context
    created = people.create_authorization_case(people.AuthorizationCaseCreate(user_id=subject.id, requested_rule_id=rule.id, nomination_reason="Verify personal evidence scope"), ctx=ctx, db=db_session)
    db_session.add(QualityAuthorizationEvidence(amo_id=ctx.amo_id, case_id=created["case"]["id"], evidence_type="OTHER", label="Another person's evidence", original_filename="restricted.pdf", storage_path="PRIVATE", size_bytes=10))
    db_session.commit()
    monkeypatch.setattr(vault, "has_quality_permission", lambda db, ctx, permission: permission == "qms.people.view")
    monkeypatch.setattr(vault, "_can_view_tenant_authorization_register", lambda db, ctx: False)
    assert vault.read_evidence_register(db_session, ctx)["total"] == 0


def test_vault_reads_retained_legacy_columns_without_storage_paths(db_session, authorization_context):
    from sqlalchemy import text
    ctx, _, _ = authorization_context
    db_session.execute(text("CREATE TABLE qms_evidence_files (id VARCHAR PRIMARY KEY, amo_id VARCHAR, name VARCHAR, storage_path VARCHAR, deleted_at TIMESTAMP)"))
    try:
        db_session.execute(text("INSERT INTO qms_evidence_files (id,amo_id,name,storage_path) VALUES ('retained-1',:amo,'Legacy certificate.pdf','PRIVATE-STORAGE')"), {"amo": ctx.amo_id})
        result = vault.read_evidence_register(db_session, ctx, q="Legacy certificate")
        assert result["total"] == 1
        item = result["items"][0]
        assert item["filename"] == "Legacy certificate.pdf"
        assert item["size_bytes"] is None and item["sha256"] is None
        assert item["download_url"].endswith("/files/retained-1/download")
        assert "PRIVATE-STORAGE" not in json.dumps(result, default=str)
    finally:
        db_session.execute(text("DROP TABLE qms_evidence_files"))


def test_vault_archive_index_excludes_executed_dispositions(db_session, authorization_context):
    from amodb.apps.quality.audit_archive_governance_models import QualityAuditArchiveManifest as Archive, QualityAuditDispositionEvent as Disposition, QualityAuditRetentionPolicyRevision as Policy
    ctx, _, _ = authorization_context
    for model in [Policy, Archive, Disposition]:
        model.__table__.create(db_session.get_bind(), checkfirst=True)
    finding = _finding(db_session, amo_id=ctx.amo_id)
    policy = Policy(amo_id=ctx.amo_id, revision_no=1, retention_class="TEST", retention_start_event="EXECUTION_CLOSED", indefinite=True, governing_basis="Isolated verification", disposition_mode="NO_DISPOSITION", approving_capability="qms.audit.view")
    db_session.add(policy); db_session.flush()
    archive = Archive(amo_id=ctx.amo_id, audit_id=finding.audit_id, manifest_version=1, retention_policy_revision_id=policy.id, retention_class="TEST", retention_start_at=datetime.now(timezone.utc), manifest_json={}, manifest_sha256="a"*64, item_count=0, package_file_ref="PRIVATE-ARCHIVE", package_filename="Audit package.zip", package_sha256="b"*64)
    db_session.add(archive); db_session.commit()
    result = vault.read_evidence_register(db_session, ctx, archives=True)
    assert result["total"] == 1
    assert result["items"][0]["download_url"].endswith(f"/archive-manifests/{archive.id}/download")
    db_session.add(Disposition(amo_id=ctx.amo_id, audit_id=finding.audit_id, manifest_id=archive.id, event_type="EXECUTED", disposition_mode="NO_DISPOSITION", inventory_sha256="c"*64, reason="Isolated disposition verification"))
    db_session.commit()
    assert vault.read_evidence_register(db_session, ctx, archives=True)["total"] == 0
