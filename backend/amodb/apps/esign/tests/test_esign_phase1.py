from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from reportlab.pdfgen import canvas
from sqlalchemy import String, create_engine
from sqlalchemy.orm import sessionmaker

from amodb.apps.esign import config, models, providers, schemas, services, utils


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    models.ESignWebAuthnCredential.__table__.c.transports.type = String(255)
    for table in [
        models.ESignDocumentVersion.__table__,
        models.ESignSignaturePolicy.__table__,
        models.ESignSignatureRequest.__table__,
        models.ESignSigner.__table__,
        models.ESignSigningIntent.__table__,
        models.ESignSignedArtifact.__table__,
        models.ESignVerificationToken.__table__,
        models.ESignWebAuthnChallenge.__table__,
        models.ESignWebAuthnCredential.__table__,
        models.ESignProviderEvent.__table__,
        models.ESignPolicyOverride.__table__,
        models.ESignEvidenceBundle.__table__,
        models.ESignNotification.__table__,
    ]:
        table.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    yield db
    db.close()


def _user(amo_id="amo-1", user_id="u-1", role="AMO_ADMIN"):
    return SimpleNamespace(amo_id=amo_id, id=user_id, full_name="Test User", email="test@example.com", webauthn_registered=True, is_superuser=False, role=role)


def _pdf(path):
    c = canvas.Canvas(str(path))
    c.drawString(72, 700, "hello")
    c.save()


def _seed_request(db, user, source, policy_code=None):
    out = services.create_signature_request(
        db,
        user,
        schemas.RequestCreateIn(
            document_id="DOC-1",
            source_storage_ref=str(source),
            title="Approval",
            policy_code=policy_code,
            signers=[schemas.SignerIn(signer_type=models.SignerType.INTERNAL_USER.value, user_id=user.id, display_name="Signer")],
            field_placements=[schemas.FieldPlacement(x=90, y=90)],
        ),
    )
    intent = db.query(models.ESignSigningIntent).first()
    req = db.query(models.ESignSignatureRequest).filter_by(id=out.request_id).one()
    return out, req, intent


def test_policy_resolution_precedence(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    p = models.ESignSignaturePolicy(tenant_id=user.amo_id, policy_code="CRIT", display_name="Critical", minimum_level=models.SignaturePolicyLevel.CRYPTO_REQUIRED.value)
    db_session.add(p)
    source = tmp_path / "a.pdf"; _pdf(source)
    out, req, _ = _seed_request(db_session, user, source, policy_code="CRIT")
    assert out.policy_code == "CRIT"
    assert req.policy_id == p.id


def test_crypto_required_blocks_appearance_without_fallback(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "assertion_verify", lambda *args, **kwargs: None)
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    p = models.ESignSignaturePolicy(tenant_id=user.amo_id, policy_code="NOFB", display_name="No fallback", minimum_level=models.SignaturePolicyLevel.CRYPTO_REQUIRED.value, allow_fallback_to_appearance=False)
    db_session.add(p)
    source = tmp_path / "b.pdf"; _pdf(source)
    _, req, intent = _seed_request(db_session, user, source, policy_code="NOFB")

    class FailProvider:
        name = "external_pades"

        def sign_pdf(self, *_args, **_kwargs):
            raise RuntimeError("fail")

        def validate_pdf(self, *_args, **_kwargs):
            raise RuntimeError("fail")

        def healthcheck(self):
            return {"ok": True}

    monkeypatch.setattr(services, "get_signing_provider", lambda: FailProvider())
    monkeypatch.setattr(services, "_CFG", config.ESignConfig("localhost", ["http://localhost:5173"], True, 300, 900, 32, "external_pades", "s", "v", 10, "none", None, "r", "l", True, False, False, False, "http://portal.local", "/verify/{token}"))

    with pytest.raises(Exception):
        services.verify_and_sign_intent(db_session, user, intent.id, credential={})


def test_crypto_required_fallback_allowed_with_override(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "assertion_verify", lambda *args, **kwargs: None)
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    p = models.ESignSignaturePolicy(tenant_id=user.amo_id, policy_code="NEEDCRYPTO", display_name="Need crypto", minimum_level=models.SignaturePolicyLevel.CRYPTO_REQUIRED.value, allow_fallback_to_appearance=False)
    db_session.add(p)
    source = tmp_path / "c.pdf"; _pdf(source)
    _, req, intent = _seed_request(db_session, user, source, policy_code="NEEDCRYPTO")
    ov = models.ESignPolicyOverride(tenant_id=user.amo_id, request_id=req.id, override_type=models.OverrideType.ALLOW_FALLBACK.value, justification="Emergency", created_by_user_id=user.id)
    db_session.add(ov)
    db_session.commit()

    class FailProvider:
        name = "external_pades"

        def sign_pdf(self, *_args, **_kwargs):
            raise RuntimeError("fail")

        def validate_pdf(self, *_args, **_kwargs):
            raise RuntimeError("fail")

        def healthcheck(self):
            return {"ok": True}

    monkeypatch.setattr(services, "get_signing_provider", lambda: FailProvider())
    monkeypatch.setattr(services, "_CFG", config.ESignConfig("localhost", ["http://localhost:5173"], True, 300, 900, 32, "external_pades", "s", "v", 10, "none", None, "r", "l", True, False, False, False, "http://portal.local", "/verify/{token}"))
    out = services.verify_and_sign_intent(db_session, user, intent.id, credential={})
    art = db_session.query(models.ESignSignedArtifact).filter_by(id=out["artifact_id"]).one()
    assert art.cryptographic_signature_applied is False


def test_timestamp_required_policy_fails_without_timestamp(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "assertion_verify", lambda *args, **kwargs: None)
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    p = models.ESignSignaturePolicy(tenant_id=user.amo_id, policy_code="TSREQ", display_name="Timestamp req", minimum_level=models.SignaturePolicyLevel.CRYPTO_AND_TIMESTAMP_REQUIRED.value, require_timestamp=True, allow_fallback_to_appearance=False)
    db_session.add(p)
    source = tmp_path / "d.pdf"; _pdf(source)
    _, _, intent = _seed_request(db_session, user, source, policy_code="TSREQ")

    class NoTsProvider:
        name = "external_pades"

        def sign_pdf(self, input_pdf_bytes, _ctx):
            return providers.SignResult(input_pdf_bytes + b"x", True, True, "external_pades", "tx", "CN=A", "1", utils.now_utc(), False, {})

        def validate_pdf(self, *_args, **_kwargs):
            return providers.ValidationResult(True, True, "CN=A", "1", utils.now_utc(), False, None, True, True, {"ok": True}, {})

        def healthcheck(self):
            return {"ok": True}

    monkeypatch.setattr(services, "get_signing_provider", lambda: NoTsProvider())
    with pytest.raises(Exception):
        services.verify_and_sign_intent(db_session, user, intent.id, credential={})


def test_achieved_level_computation(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "assertion_verify", lambda *args, **kwargs: None)
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    source = tmp_path / "e.pdf"; _pdf(source)
    _, req, intent = _seed_request(db_session, user, source)

    class CryptoTsProvider:
        name = "external_pades"

        def sign_pdf(self, input_pdf_bytes, _ctx):
            return providers.SignResult(input_pdf_bytes + b"x", True, True, "external_pades", "tx", "CN=A", "1", utils.now_utc(), True, {})

        def validate_pdf(self, *_args, **_kwargs):
            return providers.ValidationResult(True, True, "CN=A", "1", utils.now_utc(), True, True, True, True, {"ok": True}, {})

        def healthcheck(self):
            return {"ok": True}

    monkeypatch.setattr(services, "get_signing_provider", lambda: CryptoTsProvider())
    out = services.verify_and_sign_intent(db_session, user, intent.id, credential={})
    req2 = db_session.query(models.ESignSignatureRequest).filter_by(id=req.id).one()
    assert req2.achieved_level == models.SignaturePolicyLevel.CRYPTO_AND_TIMESTAMP_REQUIRED.value


def test_evidence_bundle_generation_and_download_scope(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "assertion_verify", lambda *args, **kwargs: None)
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    source = tmp_path / "f.pdf"; _pdf(source)
    _, req, intent = _seed_request(db_session, user, source)
    monkeypatch.setattr(services, "get_signing_provider", lambda: providers.AppearanceOnlyProvider())
    services.verify_and_sign_intent(db_session, user, intent.id, credential={})

    bundle = services.create_evidence_bundle(db_session, user, req.id)
    row = services.get_evidence_bundle(db_session, user, bundle.bundle_id)
    assert row.bundle_sha256
    assert Path(row.storage_ref).exists()

    other = _user("amo-2", "u2")
    with pytest.raises(Exception):
        services.get_evidence_bundle(db_session, other, bundle.bundle_id)


def test_readiness_reports_blocking_issues(db_session, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()

    class DownProvider:
        name = "external_pades"

        def healthcheck(self):
            return {"ok": False, "message": "down", "timestamp_capable": False}

    monkeypatch.setattr(services, "get_signing_provider", lambda: DownProvider())
    monkeypatch.setattr(services, "_CFG", config.ESignConfig("localhost", ["http://localhost:5173"], True, 300, 900, 32, "external_pades", "s", "v", 10, "none", None, "r", "l", True, False, False, False, "http://portal.local", "/verify/{token}"))
    ready = services.provider_readiness(db_session, user)
    assert ready.health_ok is False
    assert "provider_unreachable" in ready.blocking_issues


def test_revalidation_policy_trigger_and_skip(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    source = tmp_path / "g.pdf"; _pdf(source)
    policy = models.ESignSignaturePolicy(tenant_id=user.amo_id, policy_code="RVAL", display_name="Reval", minimum_level=models.SignaturePolicyLevel.CRYPTO_REQUIRED.value, require_revalidation_on_verify=True, revalidation_ttl_minutes=1)
    db_session.add(policy); db_session.flush()
    dv = models.ESignDocumentVersion(tenant_id=user.amo_id, document_id="D", version_no=1, storage_ref=str(source), content_sha256=utils.sha256_hex_bytes(source.read_bytes()))
    db_session.add(dv); db_session.flush()
    req = models.ESignSignatureRequest(tenant_id=user.amo_id, doc_version_id=dv.id, policy_id=policy.id, title="T", created_by_user_id=user.id, achieved_level=models.SignaturePolicyLevel.CRYPTO_REQUIRED.value)
    db_session.add(req); db_session.flush()
    art = models.ESignSignedArtifact(tenant_id=user.amo_id, signature_request_id=req.id, doc_version_id=dv.id, storage_ref=str(source), signed_content_sha256=utils.sha256_hex_bytes(source.read_bytes()), cryptographic_signature_applied=True, validation_last_checked_at=utils.now_utc() - timedelta(minutes=5))
    db_session.add(art); db_session.flush()
    tok = models.ESignVerificationToken(tenant_id=user.amo_id, artifact_id=art.id, token="tok")
    db_session.add(tok)
    signer = models.ESignSigner(tenant_id=user.amo_id, signature_request_id=req.id, signer_type=models.SignerType.INTERNAL_USER.value)
    db_session.add(signer)
    db_session.commit()

    class Provider:
        name = "external_pades"

        def validate_pdf(self, *_args, **_kwargs):
            return providers.ValidationResult(True, True, "CN=A", "1", utils.now_utc(), True, True, True, True, {"ok": True}, {})

        def sign_pdf(self, *_args, **_kwargs):
            raise RuntimeError

        def healthcheck(self):
            return {"ok": True}

    monkeypatch.setattr(services, "get_signing_provider", lambda: Provider())
    out = services.verify_public_token(db_session, "tok")
    assert out.cryptographically_valid is True


def test_override_permission_gate_and_audit(db_session, tmp_path, monkeypatch):
    actions = []
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: actions.append(kwargs.get("action")))
    admin = _user()
    source = tmp_path / "h.pdf"; _pdf(source)
    _, req, _ = _seed_request(db_session, admin, source)

    ov = services.create_override(db_session, admin, req.id, schemas.PolicyOverrideIn(override_type=models.OverrideType.ALLOW_FALLBACK.value, justification="Incident"))
    assert ov.override_type == models.OverrideType.ALLOW_FALLBACK.value
    assert "POLICY_OVERRIDE_CREATED" in actions


def test_public_verify_policy_compliant_no_internal_leak(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    source = tmp_path / "i.pdf"; _pdf(source)
    p = models.ESignSignaturePolicy(tenant_id=user.amo_id, policy_code="PUB", display_name="Public", minimum_level=models.SignaturePolicyLevel.APPEARANCE_ONLY_ALLOWED.value)
    db_session.add(p); db_session.flush()
    dv = models.ESignDocumentVersion(tenant_id=user.amo_id, document_id="D", version_no=1, storage_ref=str(source), content_sha256=utils.sha256_hex_bytes(source.read_bytes()))
    db_session.add(dv); db_session.flush()
    req = models.ESignSignatureRequest(tenant_id=user.amo_id, doc_version_id=dv.id, policy_id=p.id, title="Public", created_by_user_id=user.id, achieved_level=models.SignaturePolicyLevel.APPEARANCE_ONLY_ALLOWED.value)
    db_session.add(req); db_session.flush()
    art = models.ESignSignedArtifact(tenant_id=user.amo_id, signature_request_id=req.id, doc_version_id=dv.id, storage_ref=str(source), signed_content_sha256=utils.sha256_hex_bytes(source.read_bytes()), appearance_applied=True, cryptographic_signature_applied=False)
    db_session.add(art); db_session.flush()
    signer = models.ESignSigner(tenant_id=user.amo_id, signature_request_id=req.id, signer_type=models.SignerType.EXTERNAL_EMAIL.value, email="person@example.com", status=models.SignerStatus.APPROVED.value)
    db_session.add(signer)
    tok = models.ESignVerificationToken(tenant_id=user.amo_id, artifact_id=art.id, token="pubtok")
    db_session.add(tok); db_session.commit()

    out = services.verify_public_token(db_session, "pubtok")
    assert out.policy_compliant is True
    assert out.policy_code == "PUB"
    assert out.signers[0]["email"].startswith("p***")


def test_trust_summary_aggregates(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    source = tmp_path / "j.pdf"; _pdf(source)
    p = models.ESignSignaturePolicy(tenant_id=user.amo_id, policy_code="SUM", display_name="Summary", minimum_level=models.SignaturePolicyLevel.APPEARANCE_ONLY_ALLOWED.value)
    db_session.add(p); db_session.flush()
    dv = models.ESignDocumentVersion(tenant_id=user.amo_id, document_id="D", version_no=1, storage_ref=str(source), content_sha256=utils.sha256_hex_bytes(source.read_bytes()))
    db_session.add(dv); db_session.flush()
    r1 = models.ESignSignatureRequest(tenant_id=user.amo_id, doc_version_id=dv.id, policy_id=p.id, title="1", created_by_user_id=user.id, status=models.SignatureRequestStatus.COMPLETED.value, achieved_level=models.SignaturePolicyLevel.APPEARANCE_ONLY_ALLOWED.value)
    r2 = models.ESignSignatureRequest(tenant_id=user.amo_id, doc_version_id=dv.id, policy_id=p.id, title="2", created_by_user_id=user.id, status=models.SignatureRequestStatus.COMPLETED.value, achieved_level=models.SignaturePolicyLevel.CRYPTO_REQUIRED.value, finalized_with_fallback=True)
    db_session.add_all([r1, r2]); db_session.flush()
    a2 = models.ESignSignedArtifact(tenant_id=user.amo_id, signature_request_id=r2.id, doc_version_id=dv.id, storage_ref=str(source), signed_content_sha256=utils.sha256_hex_bytes(source.read_bytes()), cryptographic_validation_status=models.CryptoValidationStatus.ERROR.value)
    db_session.add(a2)
    db_session.commit()

    out = services.trust_summary(db_session, user)
    assert out.total_requests >= 2
    assert out.completed_requests >= 2
    assert out.fallback_count >= 1

def test_public_verify_url_builder_uses_config(monkeypatch):
    monkeypatch.setattr(
        services,
        "_CFG",
        config.ESignConfig(
            "localhost",
            ["http://localhost:5173"],
            True,
            300,
            900,
            32,
            "appearance",
            None,
            None,
            10,
            "none",
            None,
            "r",
            "l",
            True,
            False,
            False,
            False,
            "https://portal.example.com/",
            "verify/{token}",
        ),
    )
    assert services.build_public_verify_url("abc") == "https://portal.example.com/verify/abc"


def test_regenerate_verify_link_revokes_old_token(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    source = tmp_path / "k.pdf"; _pdf(source)
    dv = models.ESignDocumentVersion(tenant_id=user.amo_id, document_id="D", version_no=1, storage_ref=str(source), content_sha256=utils.sha256_hex_bytes(source.read_bytes()))
    db_session.add(dv); db_session.flush()
    req = models.ESignSignatureRequest(tenant_id=user.amo_id, doc_version_id=dv.id, title="Req", created_by_user_id=user.id)
    db_session.add(req); db_session.flush()
    art = models.ESignSignedArtifact(tenant_id=user.amo_id, signature_request_id=req.id, doc_version_id=dv.id, storage_ref=str(source), signed_content_sha256=utils.sha256_hex_bytes(source.read_bytes()))
    db_session.add(art); db_session.flush()
    t1 = models.ESignVerificationToken(tenant_id=user.amo_id, artifact_id=art.id, token="tok-old")
    db_session.add(t1); db_session.commit()

    out = services.regenerate_artifact_verify_link(db_session, user, art.id)
    assert out.token_status == "ACTIVE"

    rows = db_session.query(models.ESignVerificationToken).filter(models.ESignVerificationToken.artifact_id == art.id).all()
    assert len(rows) == 2
    old = [r for r in rows if r.token == "tok-old"][0]
    assert old.revoked_at is not None


def test_get_verify_link_tenant_scoped(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    owner = _user(amo_id="amo-1", user_id="u1")
    other = _user(amo_id="amo-2", user_id="u2")
    source = tmp_path / "l.pdf"; _pdf(source)
    dv = models.ESignDocumentVersion(tenant_id=owner.amo_id, document_id="D", version_no=1, storage_ref=str(source), content_sha256=utils.sha256_hex_bytes(source.read_bytes()))
    db_session.add(dv); db_session.flush()
    req = models.ESignSignatureRequest(tenant_id=owner.amo_id, doc_version_id=dv.id, title="Req", created_by_user_id=owner.id)
    db_session.add(req); db_session.flush()
    art = models.ESignSignedArtifact(tenant_id=owner.amo_id, signature_request_id=req.id, doc_version_id=dv.id, storage_ref=str(source), signed_content_sha256=utils.sha256_hex_bytes(source.read_bytes()))
    db_session.add(art); db_session.flush()
    db_session.add(models.ESignVerificationToken(tenant_id=owner.amo_id, artifact_id=art.id, token="tok-owner"))
    db_session.commit()

    with pytest.raises(Exception):
        services.get_artifact_verify_link(db_session, other, art.id)

def test_private_artifact_access_policy_denied(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    source = tmp_path / "m.pdf"; _pdf(source)
    policy = models.ESignSignaturePolicy(
        tenant_id=user.amo_id,
        policy_code="NOACCESS",
        display_name="No private download",
        allow_private_artifact_preview=False,
        allow_private_artifact_download=False,
    )
    db_session.add(policy); db_session.flush()
    dv = models.ESignDocumentVersion(tenant_id=user.amo_id, document_id="D", version_no=1, storage_ref=str(source), content_sha256=utils.sha256_hex_bytes(source.read_bytes()))
    db_session.add(dv); db_session.flush()
    req = models.ESignSignatureRequest(tenant_id=user.amo_id, doc_version_id=dv.id, policy_id=policy.id, title="Req", created_by_user_id=user.id)
    db_session.add(req); db_session.flush()
    art = models.ESignSignedArtifact(tenant_id=user.amo_id, signature_request_id=req.id, doc_version_id=dv.id, storage_ref=str(source), signed_content_sha256=utils.sha256_hex_bytes(source.read_bytes()))
    db_session.add(art); db_session.commit()

    with pytest.raises(Exception):
        services.private_artifact_path_for_download(db_session, user, art.id)


def test_public_access_valid_record_but_download_disallowed(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    source = tmp_path / "n.pdf"; _pdf(source)
    policy = models.ESignSignaturePolicy(tenant_id=user.amo_id, policy_code="PUBNO", display_name="No public dl", allow_public_artifact_download=False)
    db_session.add(policy); db_session.flush()
    dv = models.ESignDocumentVersion(tenant_id=user.amo_id, document_id="D", version_no=1, storage_ref=str(source), content_sha256=utils.sha256_hex_bytes(source.read_bytes()))
    db_session.add(dv); db_session.flush()
    req = models.ESignSignatureRequest(tenant_id=user.amo_id, doc_version_id=dv.id, policy_id=policy.id, title="Req", created_by_user_id=user.id)
    db_session.add(req); db_session.flush()
    art = models.ESignSignedArtifact(tenant_id=user.amo_id, signature_request_id=req.id, doc_version_id=dv.id, storage_ref=str(source), signed_content_sha256=utils.sha256_hex_bytes(source.read_bytes()))
    db_session.add(art); db_session.flush()
    db_session.add(models.ESignSigner(tenant_id=user.amo_id, signature_request_id=req.id, signer_type=models.SignerType.INTERNAL_USER.value))
    tok = models.ESignVerificationToken(tenant_id=user.amo_id, artifact_id=art.id, token="tok-deny")
    db_session.add(tok); db_session.commit()

    out = services.public_artifact_access(db_session, "tok-deny")
    assert out.artifact_available is True
    assert out.public_download_allowed is False
    with pytest.raises(Exception):
        services.public_artifact_download_path(db_session, "tok-deny")


def test_compare_hash_match_and_non_match(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    source = tmp_path / "o.pdf"; _pdf(source)
    dv = models.ESignDocumentVersion(tenant_id=user.amo_id, document_id="D", version_no=1, storage_ref=str(source), content_sha256=utils.sha256_hex_bytes(source.read_bytes()))
    db_session.add(dv); db_session.flush()
    req = models.ESignSignatureRequest(tenant_id=user.amo_id, doc_version_id=dv.id, title="Req", created_by_user_id=user.id)
    db_session.add(req); db_session.flush()
    art = models.ESignSignedArtifact(tenant_id=user.amo_id, signature_request_id=req.id, doc_version_id=dv.id, storage_ref=str(source), signed_content_sha256=utils.sha256_hex_bytes(source.read_bytes()))
    db_session.add(art); db_session.flush()
    db_session.add(models.ESignSigner(tenant_id=user.amo_id, signature_request_id=req.id, signer_type=models.SignerType.INTERNAL_USER.value))
    db_session.add(models.ESignVerificationToken(tenant_id=user.amo_id, artifact_id=art.id, token="tok-cmp"))
    db_session.commit()

    ok = services.compare_artifact_hash_private(db_session, user, art.id, schemas.HashCompareIn(provided_sha256=art.signed_content_sha256))
    assert ok.match is True
    no = services.compare_artifact_hash_public(db_session, "tok-cmp", schemas.HashCompareIn(provided_sha256="deadbeef"))
    assert no.match is False


def test_list_webauthn_credentials_masks_and_scopes(db_session, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    cred = models.ESignWebAuthnCredential(
        tenant_id=user.amo_id,
        owner_type=models.SignerType.INTERNAL_USER.value,
        owner_id=user.id,
        credential_id=b"credential-abc-1234567890",
        public_key=b"pk",
        sign_count=0,
        transports="internal",
    )
    db_session.add(cred)
    db_session.commit()

    rows = services.list_webauthn_credentials(db_session, user)
    assert len(rows) == 1
    assert rows[0].credential_id_masked

    other = _user("amo-2", "u-2")
    assert services.list_webauthn_credentials(db_session, other) == []


def test_deactivate_webauthn_credential_marks_inactive(db_session, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    cred = models.ESignWebAuthnCredential(
        tenant_id=user.amo_id,
        owner_type=models.SignerType.INTERNAL_USER.value,
        owner_id=user.id,
        credential_id=b"credential-xyz-1234567890",
        public_key=b"pk",
        sign_count=0,
        transports="internal",
        is_active=True,
    )
    db_session.add(cred)
    db_session.commit()

    services.deactivate_webauthn_credential(db_session, user, cred.id)
    updated = db_session.query(models.ESignWebAuthnCredential).filter_by(id=cred.id).one()
    assert updated.is_active is False


def test_rename_webauthn_credential_success_and_audit(db_session, monkeypatch):
    actions = []

    def _capture(*_args, **kwargs):
        actions.append(kwargs.get("action"))

    monkeypatch.setattr(services, "_audit", _capture)
    user = _user()
    cred = models.ESignWebAuthnCredential(
        tenant_id=user.amo_id,
        owner_type=models.WebAuthnOwnerType.USER.value,
        owner_id=user.id,
        credential_id=b"credential-rename-1",
        public_key=b"pk",
        sign_count=0,
        is_active=True,
    )
    db_session.add(cred)
    db_session.commit()

    renamed = services.rename_webauthn_credential(db_session, user, cred.id, "Laptop Key")
    assert renamed.nickname == "Laptop Key"
    assert renamed.updated_at is not None
    assert "WEB_AUTHN_CREDENTIAL_RENAMED" in actions


def test_rename_webauthn_credential_denied_for_non_owner(db_session, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    owner = _user("amo-1", "u-owner", role="TECH")
    other = _user("amo-1", "u-other", role="TECH")
    cred = models.ESignWebAuthnCredential(
        tenant_id=owner.amo_id,
        owner_type=models.WebAuthnOwnerType.USER.value,
        owner_id=owner.id,
        credential_id=b"credential-rename-2",
        public_key=b"pk",
        sign_count=0,
        is_active=True,
    )
    db_session.add(cred)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        services.rename_webauthn_credential(db_session, other, cred.id, "Other")
    assert exc.value.status_code == 403


def test_rename_webauthn_credential_validation(db_session, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user()
    cred = models.ESignWebAuthnCredential(
        tenant_id=user.amo_id,
        owner_type=models.WebAuthnOwnerType.USER.value,
        owner_id=user.id,
        credential_id=b"credential-rename-3",
        public_key=b"pk",
        sign_count=0,
        is_active=True,
    )
    db_session.add(cred)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        services.rename_webauthn_credential(db_session, user, cred.id, "x" * 51)
    assert exc.value.status_code == 422


def test_inbox_only_returns_current_user_items_and_count(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user("amo-1", "u-1")
    other = _user("amo-1", "u-2")
    source = tmp_path / "inbox.pdf"; _pdf(source)

    out, req, intent = _seed_request(db_session, user, source)
    signer_for_user = db_session.query(models.ESignSigner).filter_by(signature_request_id=req.id, user_id=user.id).one()
    signer_for_user.status = models.SignerStatus.PENDING.value

    signer_for_other = models.ESignSigner(
        tenant_id=user.amo_id,
        signature_request_id=req.id,
        signer_type=models.SignerType.INTERNAL_USER.value,
        user_id=other.id,
        status=models.SignerStatus.PENDING.value,
    )
    db_session.add(signer_for_other)
    db_session.commit()

    inbox_user = services.list_signing_inbox(db_session, user)
    assert inbox_user.total == 1
    assert inbox_user.items[0].intent_id == intent.id

    inbox_other = services.list_signing_inbox(db_session, other)
    assert inbox_other.total == 1
    assert inbox_other.items[0].signer_id == signer_for_other.id

    counts = services.inbox_count(db_session, user)
    assert counts.pending_count == 1

def test_inbox_pagination_stable_order(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user("amo-1", "u-1")
    for i in range(3):
      source = tmp_path / f"inbox-{i}.pdf"; _pdf(source)
      _seed_request(db_session, user, source)

    out1 = services.list_signing_inbox(db_session, user, page=1, page_size=2)
    out2 = services.list_signing_inbox(db_session, user, page=2, page_size=2)
    assert out1.total >= 3
    ids1 = [item.signature_request_id for item in out1.items]
    ids2 = [item.signature_request_id for item in out2.items]
    assert set(ids1).isdisjoint(set(ids2))


def test_notification_created_on_send_and_user_scoped(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    sender = _user("amo-1", "admin")
    signer_user = _user("amo-1", "signer")
    source = tmp_path / "notif-send.pdf"; _pdf(source)

    out = services.create_signature_request(
        db_session,
        sender,
        schemas.RequestCreateIn(
            document_id="DOC-N",
            source_storage_ref=str(source),
            title="Needs signature",
            signers=[schemas.SignerIn(signer_type=models.SignerType.INTERNAL_USER.value, user_id=signer_user.id, display_name="Signer")],
            field_placements=[schemas.FieldPlacement(x=10, y=10)],
        ),
    )
    services.send_request(db_session, sender, out.request_id)

    notes_for_signer = services.list_notifications(db_session, signer_user)
    assert len(notes_for_signer) == 1
    assert notes_for_signer[0].type == models.NotificationType.SIGNATURE_REQUESTED.value

    other = _user("amo-1", "other")
    assert services.list_notifications(db_session, other) == []


def test_notification_count_and_read_and_dismiss(db_session, monkeypatch):
    monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
    user = _user("amo-1", "u-1")
    services._create_notification(
        db_session,
        tenant_id=user.amo_id,
        user_id=user.id,
        notification_type=models.NotificationType.SIGNATURE_REQUESTED.value,
        title="Signature requested",
        body="Please review",
        link_path="/maintenance/amo-1/quality/esign/inbox",
        actor_user_id=user.id,
    )
    db_session.commit()

    count = services.notification_count(db_session, user)
    assert count.unread_count == 1
    note = services.list_notifications(db_session, user)[0]

    read = services.mark_notification_read(db_session, user, note.id)
    assert read.read_at is not None

    count_after_read = services.notification_count(db_session, user)
    assert count_after_read.unread_count == 0

    services.dismiss_notification(db_session, user, note.id)
    assert services.list_notifications(db_session, user) == []
