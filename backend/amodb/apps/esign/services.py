from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import threading
import time
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import services as audit_services

from . import config, models, providers, schemas, utils

_CFG = config.load_config()
_WEBAUTHN_WINDOW_SEC = int(os.getenv("ESIGN_WEBAUTHN_RATE_LIMIT_WINDOW_SEC", "60") or "60")
_WEBAUTHN_MAX_ATTEMPTS = int(os.getenv("ESIGN_WEBAUTHN_RATE_LIMIT_MAX_ATTEMPTS", "20") or "20")
_RATE_LIMIT_STATE: dict[tuple[str, str, str], list[float]] = {}
_RATE_LIMIT_LOCK = threading.Lock()
_ESIGN_STORAGE = utils.ensure_dir(Path(os.getenv("ESIGN_STORAGE_DIR", "uploads/esign")).resolve())


class VerifyTokenNotFound(Exception):
    pass


def validate_runtime_config() -> None:
    config.validate_config(_CFG)
    if _CFG.provider_mode == "external_pades" and _CFG.provider_healthcheck_on_startup:
        health = get_signing_provider().healthcheck()
        if not health.get("ok", False):
            raise RuntimeError("E-sign external provider healthcheck failed")


def _audit(db: Session, *, amo_id: str, actor_user_id: str | None, entity_type: str, entity_id: str, action: str, after: dict | None = None):
    audit_services.log_event(db, amo_id=amo_id, actor_user_id=actor_user_id, entity_type=entity_type, entity_id=entity_id, action=action, after=after, metadata={"module": "esign"})


def _provider_event(db: Session, *, tenant_id: str, provider_name: str, direction: str, event_type: str, artifact_id: str | None = None, request_id: str | None = None, payload: dict[str, Any] | None = None):
    db.add(models.ESignProviderEvent(tenant_id=tenant_id, artifact_id=artifact_id, request_id=request_id, provider_name=provider_name, direction=direction, event_type=event_type, sanitized_payload_json=payload))


def _mask_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def build_public_verify_url(token: str) -> str:
    base = (_CFG.public_verify_base_url or "").rstrip("/")
    path_template = _CFG.public_verify_path_template or "/verify/{token}"
    path = path_template.format(token=token)
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def _create_artifact_token(db: Session, *, tenant_id: str, artifact_id: str, actor_user_id: str | None) -> tuple[models.ESignVerificationToken, str, str]:
    token_raw = utils.random_token(_CFG.verify_token_bytes)
    token = models.ESignVerificationToken(
        tenant_id=tenant_id,
        artifact_id=artifact_id,
        token=token_raw,
        expires_at=utils.now_utc() + timedelta(days=180),
    )
    db.add(token)
    db.flush()
    verify_url = build_public_verify_url(token_raw)
    _audit(db, amo_id=tenant_id, actor_user_id=actor_user_id, entity_type="esign_token", entity_id=token.id, action="VERIFY_TOKEN_CREATED_FOR_ARTIFACT", after={"artifact_id": artifact_id, "token_ref": _mask_token(token_raw)})
    return token, token_raw, verify_url


def _mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    n, d = email.split("@", 1)
    return f"{n[:1]}***@{d}"


def _is_expired(dt) -> bool:
    if dt is None:
        return False
    now = utils.now_utc()
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=now.tzinfo) < now
    return dt < now


def _client_ip(request: Request | None) -> str:
    return request.client.host if request and request.client else "unknown"


def enforce_rate_limit(request: Request | None, tenant_id: str, key: str) -> None:
    now = time.monotonic()
    k = (tenant_id, _client_ip(request), key)
    with _RATE_LIMIT_LOCK:
        arr = [t for t in _RATE_LIMIT_STATE.get(k, []) if t >= now - _WEBAUTHN_WINDOW_SEC]
        if len(arr) >= _WEBAUTHN_MAX_ATTEMPTS:
            raise HTTPException(429, "Rate limit exceeded")
        arr.append(now)
        _RATE_LIMIT_STATE[k] = arr


def _load_webauthn():
    from webauthn import generate_authentication_options, generate_registration_options, verify_authentication_response, verify_registration_response
    from webauthn.helpers.structs import AuthenticationCredential, AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor, RegistrationCredential, UserVerificationRequirement

    return {
        "generate_registration_options": generate_registration_options,
        "verify_registration_response": verify_registration_response,
        "generate_authentication_options": generate_authentication_options,
        "verify_authentication_response": verify_authentication_response,
        "AuthenticatorSelectionCriteria": AuthenticatorSelectionCriteria,
        "UserVerificationRequirement": UserVerificationRequirement,
        "PublicKeyCredentialDescriptor": PublicKeyCredentialDescriptor,
        "RegistrationCredential": RegistrationCredential,
        "AuthenticationCredential": AuthenticationCredential,
    }


def get_signing_provider() -> providers.SigningProvider:
    if _CFG.provider_mode == "external_pades":
        return providers.ExternalPadesProvider(sign_url=_CFG.external_sign_url or "", validate_url=_CFG.external_validate_url or "", timeout_seconds=_CFG.external_timeout_seconds, auth_mode=_CFG.external_auth_mode, bearer_token=_CFG.external_bearer_token)
    return providers.AppearanceOnlyProvider()


def _resolve_policy(db: Session, tenant_id: str, policy_code: str | None) -> models.ESignSignaturePolicy:
    policy = None
    if policy_code:
        policy = db.query(models.ESignSignaturePolicy).filter(models.ESignSignaturePolicy.tenant_id == tenant_id, models.ESignSignaturePolicy.policy_code == policy_code, models.ESignSignaturePolicy.is_active.is_(True)).first()
    if not policy:
        policy = db.query(models.ESignSignaturePolicy).filter(models.ESignSignaturePolicy.tenant_id == tenant_id, models.ESignSignaturePolicy.is_active.is_(True)).order_by(models.ESignSignaturePolicy.created_at.asc()).first()
    if not policy:
        policy = models.ESignSignaturePolicy(tenant_id=tenant_id, policy_code="DEFAULT_APPEARANCE", display_name="Default appearance policy", minimum_level=models.SignaturePolicyLevel.APPEARANCE_ONLY_ALLOWED.value, allow_fallback_to_appearance=True, require_provider_health_before_finalization=False)
        db.add(policy)
        db.flush()
    return policy


def _policy_compliant(policy: models.ESignSignaturePolicy | None, achieved_level: str | None) -> bool:
    if not policy or not achieved_level:
        return False
    order = {
        models.SignaturePolicyLevel.BASIC_APPROVAL.value: 1,
        models.SignaturePolicyLevel.APPEARANCE_ONLY_ALLOWED.value: 2,
        models.SignaturePolicyLevel.CRYPTO_REQUIRED.value: 3,
        models.SignaturePolicyLevel.CRYPTO_AND_TIMESTAMP_REQUIRED.value: 4,
    }
    return order.get(achieved_level, 0) >= order.get(policy.minimum_level, 0)


def _store_challenge(db: Session, *, tenant_id: str, owner_id: str, challenge: str, challenge_type: str, request_json: dict | None = None, intent_id: str | None = None):
    db.add(models.ESignWebAuthnChallenge(tenant_id=tenant_id, owner_id=owner_id, challenge=challenge, challenge_hash=hashlib.sha256(challenge.encode("utf-8")).hexdigest(), challenge_type=challenge_type, request_json=request_json, intent_id=intent_id, expires_at=utils.now_utc() + timedelta(seconds=_CFG.challenge_ttl_seconds)))
    db.flush()


def _extract_b64_challenge_from_credential(credential: dict[str, Any]) -> str | None:
    try:
        raw = utils.b64url_decode(credential["response"]["clientDataJSON"])
        return json.loads(raw.decode("utf-8")).get("challenge")
    except Exception:
        return None


def _consume_active_challenge(db: Session, *, tenant_id: str, owner_id: str, challenge_type: str, credential: dict[str, Any], intent_id: str | None = None):
    ch = _extract_b64_challenge_from_credential(credential)
    if not ch:
        raise HTTPException(400, "Missing challenge")
    row = db.query(models.ESignWebAuthnChallenge).filter(models.ESignWebAuthnChallenge.tenant_id == tenant_id, models.ESignWebAuthnChallenge.owner_id == owner_id, models.ESignWebAuthnChallenge.challenge_type == challenge_type, models.ESignWebAuthnChallenge.challenge_hash == hashlib.sha256(ch.encode("utf-8")).hexdigest(), models.ESignWebAuthnChallenge.consumed_at.is_(None)).order_by(models.ESignWebAuthnChallenge.created_at.desc()).first()
    if not row or _is_expired(row.expires_at):
        raise HTTPException(400, "Challenge expired or invalid")
    if intent_id and row.intent_id != intent_id:
        raise HTTPException(400, "Challenge/intent mismatch")
    return row


def _artifact_path(tenant_id: str, request_id: str, artifact_id: str) -> Path:
    folder = utils.ensure_dir(_ESIGN_STORAGE / tenant_id / request_id)
    return folder / f"signed_{artifact_id}.pdf"


def _apply_validation_to_artifact(artifact: models.ESignSignedArtifact, result: providers.ValidationResult, *, source: str):
    artifact.validation_last_checked_at = utils.now_utc()
    artifact.validation_last_result_source = source
    artifact.timestamp_valid = result.timestamp_valid
    artifact.certificate_subject = result.certificate_subject
    artifact.certificate_serial = result.certificate_serial
    artifact.signing_time = result.signing_time
    artifact.validation_summary_json = result.validation_summary
    if result.cryptographically_valid:
        artifact.cryptographic_validation_status = models.CryptoValidationStatus.VALID.value
    elif result.signature_present:
        artifact.cryptographic_validation_status = models.CryptoValidationStatus.INVALID.value
    else:
        artifact.cryptographic_validation_status = models.CryptoValidationStatus.ERROR.value


def needs_revalidation(artifact: models.ESignSignedArtifact, policy: models.ESignSignaturePolicy | None, now) -> bool:
    if not artifact.cryptographic_signature_applied:
        return False
    if not policy or not policy.require_revalidation_on_verify:
        return False
    if artifact.validation_last_checked_at is None:
        return True
    ttl = policy.revalidation_ttl_minutes or 0
    if ttl <= 0:
        return True
    return artifact.validation_last_checked_at + timedelta(minutes=ttl) < now


def _active_override(db: Session, request_id: str, tenant_id: str, override_type: str) -> models.ESignPolicyOverride | None:
    now = utils.now_utc()
    return db.query(models.ESignPolicyOverride).filter(models.ESignPolicyOverride.request_id == request_id, models.ESignPolicyOverride.tenant_id == tenant_id, models.ESignPolicyOverride.override_type == override_type, models.ESignPolicyOverride.is_active.is_(True), ((models.ESignPolicyOverride.expires_at.is_(None)) | (models.ESignPolicyOverride.expires_at >= now))).order_by(models.ESignPolicyOverride.created_at.desc()).first()


def create_signature_request(db: Session, current_user: account_models.User, payload: schemas.RequestCreateIn) -> schemas.RequestCreateOut:
    tenant_id = current_user.amo_id
    source = Path(payload.source_storage_ref).read_bytes()
    digest = utils.sha256_hex_bytes(source)
    policy = _resolve_policy(db, tenant_id, payload.policy_code)

    docv = models.ESignDocumentVersion(tenant_id=tenant_id, document_id=payload.document_id, version_no=1, storage_ref=payload.source_storage_ref, content_sha256=digest, created_by_user_id=current_user.id)
    db.add(docv)
    db.flush()
    _audit(db, amo_id=tenant_id, actor_user_id=current_user.id, entity_type="esign_document_version", entity_id=docv.id, action="DOC_VERSION_CREATED", after={"content_sha256": digest})

    req = models.ESignSignatureRequest(tenant_id=tenant_id, doc_version_id=docv.id, policy_id=policy.id, status=models.SignatureRequestStatus.DRAFT.value, title=payload.title, message=payload.message, expires_at=payload.expires_at, created_by_user_id=current_user.id)
    db.add(req)
    db.flush()
    _audit(db, amo_id=tenant_id, actor_user_id=current_user.id, entity_type="esign_signature_request", entity_id=req.id, action="SIGNATURE_REQUEST_CREATED", after={"title": req.title})
    _audit(db, amo_id=tenant_id, actor_user_id=current_user.id, entity_type="esign_signature_request", entity_id=req.id, action="SIGNATURE_POLICY_RESOLVED", after={"policy_code": policy.policy_code, "minimum_level": policy.minimum_level})

    for s in payload.signers:
        signer = models.ESignSigner(tenant_id=tenant_id, signature_request_id=req.id, signer_type=s.signer_type, user_id=s.user_id, email=s.email.lower() if s.email else None, display_name=s.display_name, signing_order=s.signing_order)
        db.add(signer)
        db.flush()
        intent_payload = {"coordinates": [p.model_dump() for p in payload.field_placements], "doc_hash": digest, "doc_version_id": docv.id, "nonce": utils.random_token(24), "reason": payload.message or "approval", "signer_id": signer.id, "timestamp": utils.now_utc().isoformat()}
        intent = models.ESignSigningIntent(tenant_id=tenant_id, signer_id=signer.id, doc_version_id=docv.id, intent_sha256=utils.sha256_hex_canonical_json(intent_payload), payload_json=intent_payload, expires_at=utils.now_utc() + timedelta(seconds=_CFG.signing_intent_ttl_seconds))
        db.add(intent)
        db.flush()
        _audit(db, amo_id=tenant_id, actor_user_id=current_user.id, entity_type="esign_signing_intent", entity_id=intent.id, action="SIGNING_INTENT_CREATED", after={"intent_sha256": intent.intent_sha256})

    db.commit()
    return schemas.RequestCreateOut(request_id=req.id, doc_version_id=docv.id, doc_hash=digest, policy_code=policy.policy_code, policy_minimum_level=policy.minimum_level)


def send_request(db: Session, current_user: account_models.User, request_id: str):
    req = db.query(models.ESignSignatureRequest).filter(models.ESignSignatureRequest.id == request_id, models.ESignSignatureRequest.tenant_id == current_user.amo_id).first()
    if not req:
        raise HTTPException(404, "Request not found")
    policy = db.query(models.ESignSignaturePolicy).filter(models.ESignSignaturePolicy.id == req.policy_id).first()
    if policy and policy.require_provider_health_before_send and policy.minimum_level in {models.SignaturePolicyLevel.CRYPTO_REQUIRED.value, models.SignaturePolicyLevel.CRYPTO_AND_TIMESTAMP_REQUIRED.value}:
        health = get_signing_provider().healthcheck()
        if not health.get("ok") and not _active_override(db, req.id, current_user.amo_id, models.OverrideType.BYPASS_PROVIDER_HEALTHCHECK.value):
            _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_signature_request", entity_id=req.id, action="POLICY_BLOCKED_SEND", after={"reason": "provider_health_failed"})
            db.commit()
            raise HTTPException(409, "Policy blocked send: provider not ready")
    req.status = models.SignatureRequestStatus.SENT.value
    req.sent_at = utils.now_utc()
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_signature_request", entity_id=req.id, action="SIGNATURE_REQUEST_SENT")
    db.commit()
    return req


def get_signing_context(db: Session, current_user: account_models.User, request_id: str):
    req = db.query(models.ESignSignatureRequest).filter(models.ESignSignatureRequest.id == request_id, models.ESignSignatureRequest.tenant_id == current_user.amo_id).first()
    if not req:
        raise HTTPException(404, "Not found")
    signer = db.query(models.ESignSigner).filter(models.ESignSigner.signature_request_id == req.id, models.ESignSigner.user_id == current_user.id, models.ESignSigner.tenant_id == current_user.amo_id).first()
    if not signer:
        raise HTTPException(403, "Not a signer")
    intent = db.query(models.ESignSigningIntent).filter(models.ESignSigningIntent.signer_id == signer.id, models.ESignSigningIntent.tenant_id == current_user.amo_id).order_by(models.ESignSigningIntent.created_at.desc()).first()
    docv = db.query(models.ESignDocumentVersion).filter(models.ESignDocumentVersion.id == req.doc_version_id, models.ESignDocumentVersion.tenant_id == current_user.amo_id).first()
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_signer", entity_id=signer.id, action="SIGNER_VIEWED")
    db.commit()
    return schemas.SigningContextOut(request_id=req.id, signer_id=signer.id, status=signer.status, title=req.title, doc_hash=docv.content_sha256 if docv else "", placements=[schemas.FieldPlacement(**p) for p in (intent.payload_json.get("coordinates") if intent else [])])


def registration_options(db: Session, current_user: account_models.User, payload: schemas.RegistrationOptionsIn):
    lib = _load_webauthn()
    challenge = utils.webauthn_challenge_bytes()
    options = lib["generate_registration_options"](rp_id=_CFG.webauthn_rp_id, rp_name="AMO Portal", user_id=current_user.id.encode("utf-8"), user_name=current_user.email, user_display_name=payload.display_name or current_user.full_name or current_user.email, authenticator_selection=lib["AuthenticatorSelectionCriteria"](user_verification=lib["UserVerificationRequirement"].REQUIRED if _CFG.webauthn_require_uv else lib["UserVerificationRequirement"].PREFERRED), challenge=challenge)
    _store_challenge(db, tenant_id=current_user.amo_id, owner_id=current_user.id, challenge=utils.b64url_encode(challenge), challenge_type=models.ChallengeType.REGISTRATION.value)
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_webauthn", entity_id=current_user.id, action="WEB_AUTHN_REG_OPTIONS_ISSUED")
    db.commit()
    return options


def registration_verify(db: Session, current_user: account_models.User, credential: dict):
    lib = _load_webauthn()
    row = _consume_active_challenge(db, tenant_id=current_user.amo_id, owner_id=current_user.id, challenge_type=models.ChallengeType.REGISTRATION.value, credential=credential)
    verification = lib["verify_registration_response"](credential=lib["RegistrationCredential"].parse_obj(credential), expected_challenge=row.challenge, expected_origin=_CFG.webauthn_expected_origins, expected_rp_id=_CFG.webauthn_rp_id, require_user_verification=_CFG.webauthn_require_uv)
    cred = models.ESignWebAuthnCredential(tenant_id=current_user.amo_id, owner_type=models.WebAuthnOwnerType.USER.value, owner_id=current_user.id, credential_id=verification.credential_id, public_key=verification.credential_public_key, sign_count=verification.sign_count, attestation_format=getattr(verification, "fmt", None))
    row.consumed_at = utils.now_utc()
    db.add(cred)
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_webauthn", entity_id=current_user.id, action="WEB_AUTHN_REG_VERIFIED")
    db.commit()
    return cred


def assertion_options(db: Session, current_user: account_models.User, intent_id: str | None = None):
    lib = _load_webauthn()
    creds = db.query(models.ESignWebAuthnCredential).filter(models.ESignWebAuthnCredential.tenant_id == current_user.amo_id, models.ESignWebAuthnCredential.owner_id == current_user.id, models.ESignWebAuthnCredential.owner_type == models.WebAuthnOwnerType.USER.value, models.ESignWebAuthnCredential.is_active.is_(True)).all()
    allow = [lib["PublicKeyCredentialDescriptor"](id=c.credential_id) for c in creds]
    challenge = utils.webauthn_challenge_bytes()
    opts = lib["generate_authentication_options"](rp_id=_CFG.webauthn_rp_id, challenge=challenge, allow_credentials=allow, user_verification=lib["UserVerificationRequirement"].REQUIRED if _CFG.webauthn_require_uv else lib["UserVerificationRequirement"].PREFERRED)
    _store_challenge(db, tenant_id=current_user.amo_id, owner_id=current_user.id, challenge=utils.b64url_encode(challenge), challenge_type=models.ChallengeType.ASSERTION.value, intent_id=intent_id)
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_webauthn", entity_id=current_user.id, action="WEB_AUTHN_ASSERT_OPTIONS_ISSUED", after={"intent_id": intent_id})
    db.commit()
    return opts


def assertion_verify(db: Session, current_user: account_models.User, credential: dict, intent_id: str | None = None):
    lib = _load_webauthn()
    challenge_row = _consume_active_challenge(db, tenant_id=current_user.amo_id, owner_id=current_user.id, challenge_type=models.ChallengeType.ASSERTION.value, credential=credential, intent_id=intent_id)
    cred_id = utils.b64url_decode(credential.get("id", ""))
    cred = db.query(models.ESignWebAuthnCredential).filter(models.ESignWebAuthnCredential.tenant_id == current_user.amo_id, models.ESignWebAuthnCredential.credential_id == cred_id, models.ESignWebAuthnCredential.is_active.is_(True)).first()
    if not cred:
        raise HTTPException(404, "Credential not found")
    verification = lib["verify_authentication_response"](credential=lib["AuthenticationCredential"].parse_obj(credential), expected_challenge=challenge_row.challenge, expected_origin=_CFG.webauthn_expected_origins, expected_rp_id=_CFG.webauthn_rp_id, credential_public_key=cred.public_key, credential_current_sign_count=int(cred.sign_count), require_user_verification=_CFG.webauthn_require_uv)
    cred.sign_count = int(verification.new_sign_count)
    cred.last_used_at = utils.now_utc()
    challenge_row.consumed_at = utils.now_utc()
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_webauthn", entity_id=current_user.id, action="WEB_AUTHN_ASSERT_VERIFIED", after={"intent_id": intent_id})
    db.commit()
    return cred






def _serialize_webauthn_credential(row: models.ESignWebAuthnCredential) -> schemas.WebAuthnCredentialOut:
    raw = utils.b64url_encode(bytes(row.credential_id or b""))
    masked = f"{raw[:6]}…{raw[-4:]}" if len(raw) > 12 else raw
    transports_value = row.transports
    if isinstance(transports_value, str):
        transports = [transports_value]
    elif isinstance(transports_value, (list, tuple, set)):
        transports = [str(value) for value in transports_value if value]
    else:
        transports = []
    return schemas.WebAuthnCredentialOut(
        id=row.id,
        credential_id_masked=masked,
        nickname=row.nickname,
        transports=transports,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_used_at=row.last_used_at,
        is_active=bool(row.is_active),
    )

def list_webauthn_credentials(db: Session, current_user: account_models.User):
    rows = (
        db.query(models.ESignWebAuthnCredential)
        .filter(
            models.ESignWebAuthnCredential.tenant_id == current_user.amo_id,
            models.ESignWebAuthnCredential.owner_type.in_([models.WebAuthnOwnerType.USER.value, models.SignerType.INTERNAL_USER.value]),
            models.ESignWebAuthnCredential.owner_id == current_user.id,
        )
        .order_by(models.ESignWebAuthnCredential.created_at.desc())
        .all()
    )
    return [_serialize_webauthn_credential(row) for row in rows]




def _sanitize_credential_nickname(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = "".join(ch for ch in value if ch.isprintable() and ch not in "\r\n\t").strip()
    if cleaned == "":
        return None
    if len(cleaned) > 50:
        raise HTTPException(422, "Nickname must be 50 characters or fewer")
    return cleaned


def rename_webauthn_credential(db: Session, current_user: account_models.User, credential_id: str, nickname: str | None):
    row = db.query(models.ESignWebAuthnCredential).filter(models.ESignWebAuthnCredential.id == credential_id, models.ESignWebAuthnCredential.tenant_id == current_user.amo_id).first()
    if not row:
        raise HTTPException(404, "Credential not found")
    role = getattr(current_user.role, "value", str(getattr(current_user, "role", "")))
    is_admin = bool(getattr(current_user, "is_superuser", False) or role in {"AMO_ADMIN", "SUPERUSER"})
    if row.owner_id != current_user.id and not is_admin:
        raise HTTPException(403, "Credential rename not permitted")

    clean_nickname = _sanitize_credential_nickname(nickname)
    row.nickname = clean_nickname
    row.updated_at = utils.now_utc()
    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="esign_webauthn",
        entity_id=row.id,
        action="WEB_AUTHN_CREDENTIAL_RENAMED",
        after={"nickname": clean_nickname},
    )
    db.commit()
    return row


def list_signing_inbox(
    db: Session,
    current_user: account_models.User,
    *,
    status: str | None = None,
    date_from=None,
    date_to=None,
    page: int = 1,
    page_size: int = 20,
):
    page = max(1, int(page))
    page_size = min(100, max(1, int(page_size)))

    q = (
        db.query(models.ESignSigner, models.ESignSignatureRequest, models.ESignSignaturePolicy, models.ESignDocumentVersion)
        .join(models.ESignSignatureRequest, models.ESignSignatureRequest.id == models.ESignSigner.signature_request_id)
        .outerjoin(models.ESignSignaturePolicy, models.ESignSignaturePolicy.id == models.ESignSignatureRequest.policy_id)
        .outerjoin(models.ESignDocumentVersion, models.ESignDocumentVersion.id == models.ESignSignatureRequest.doc_version_id)
        .filter(
            models.ESignSigner.tenant_id == current_user.amo_id,
            models.ESignSigner.signer_type == models.SignerType.INTERNAL_USER.value,
            models.ESignSigner.user_id == current_user.id,
            models.ESignSignatureRequest.tenant_id == current_user.amo_id,
        )
    )

    if status:
        q = q.filter(models.ESignSigner.status == status)
    else:
        q = q.filter(models.ESignSigner.status.in_([models.SignerStatus.PENDING.value, models.SignerStatus.VIEWED.value]))

    if date_from is not None:
        q = q.filter(models.ESignSignatureRequest.created_at >= date_from)
    if date_to is not None:
        q = q.filter(models.ESignSignatureRequest.created_at <= date_to)

    total = q.count()
    rows = q.order_by(models.ESignSignatureRequest.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for signer, req, policy, docv in rows:
        intent = (
            db.query(models.ESignSigningIntent)
            .filter(models.ESignSigningIntent.tenant_id == current_user.amo_id, models.ESignSigningIntent.signer_id == signer.id)
            .order_by(models.ESignSigningIntent.created_at.desc())
            .first()
        )
        fingerprint = (docv.content_sha256 if docv and docv.content_sha256 else "")
        items.append(
            schemas.InboxItemOut(
                signature_request_id=req.id,
                signer_id=signer.id,
                intent_id=intent.id if intent else None,
                request_title=req.title,
                request_status=req.status,
                policy_code=policy.policy_code if policy else None,
                policy_minimum_level=policy.minimum_level if policy else None,
                achieved_level=req.achieved_level,
                signer_status=signer.status,
                expires_at=req.expires_at,
                created_at=req.created_at,
                requested_by=(current_user.full_name if req.created_by_user_id == current_user.id else req.created_by_user_id),
                doc_version_hash_short=(f"{fingerprint[:12]}…" if fingerprint else ""),
                sign_url=(f"/maintenance/{current_user.amo_id}/quality/esign/sign/{intent.id}" if intent else f"/maintenance/{current_user.amo_id}/quality/esign/requests/{req.id}"),
            )
        )

    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_inbox", entity_id=current_user.id, action="ESIGN_INBOX_VIEWED", after={"page": page, "page_size": page_size})
    db.commit()
    return schemas.InboxOut(items=items, page=page, page_size=page_size, total=total)


def inbox_count(db: Session, current_user: account_models.User):
    base = db.query(models.ESignSigner).join(models.ESignSignatureRequest, models.ESignSignatureRequest.id == models.ESignSigner.signature_request_id).filter(
        models.ESignSigner.tenant_id == current_user.amo_id,
        models.ESignSigner.signer_type == models.SignerType.INTERNAL_USER.value,
        models.ESignSigner.user_id == current_user.id,
        models.ESignSigner.status.in_([models.SignerStatus.PENDING.value, models.SignerStatus.VIEWED.value]),
    )
    pending = base.count()
    soon_cutoff = utils.now_utc() + timedelta(days=2)
    expiring = base.filter(models.ESignSignatureRequest.expires_at.is_not(None), models.ESignSignatureRequest.expires_at <= soon_cutoff).count()
    return schemas.InboxCountOut(pending_count=pending, expiring_soon_count=expiring)

def deactivate_webauthn_credential(db: Session, current_user: account_models.User, credential_id: str):
    row = (
        db.query(models.ESignWebAuthnCredential)
        .filter(
            models.ESignWebAuthnCredential.id == credential_id,
            models.ESignWebAuthnCredential.tenant_id == current_user.amo_id,
            models.ESignWebAuthnCredential.owner_type.in_([models.WebAuthnOwnerType.USER.value, models.SignerType.INTERNAL_USER.value]),
            models.ESignWebAuthnCredential.owner_id == current_user.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Credential not found")
    row.is_active = False
    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="esign_webauthn",
        entity_id=row.id,
        action="WEB_AUTHN_CREDENTIAL_DEACTIVATED",
    )
    db.commit()
    return row

def _validate_artifact_with_provider(db: Session, *, artifact: models.ESignSignedArtifact, req: models.ESignSignatureRequest, tenant_id: str, source: str = models.ValidationResultSource.LIVE.value):
    provider = get_signing_provider()
    _provider_event(db, tenant_id=tenant_id, provider_name=provider.name, direction=models.ProviderDirection.REQUEST.value, event_type=models.ProviderEventType.VALIDATE_ATTEMPT.value, artifact_id=artifact.id, request_id=req.id, payload={"artifact_id": artifact.id})
    _audit(db, amo_id=tenant_id, actor_user_id=None, entity_type="esign_artifact", entity_id=artifact.id, action="CRYPTO_VALIDATE_ATTEMPTED")
    try:
        res = provider.validate_pdf(Path(artifact.storage_ref).read_bytes(), {"artifact_id": artifact.id, "request_id": req.id})
        _apply_validation_to_artifact(artifact, res, source=source)
        _provider_event(db, tenant_id=tenant_id, provider_name=provider.name, direction=models.ProviderDirection.RESPONSE.value, event_type=models.ProviderEventType.VALIDATE_SUCCESS.value, artifact_id=artifact.id, request_id=req.id, payload=res.validation_summary)
        _audit(db, amo_id=tenant_id, actor_user_id=None, entity_type="esign_artifact", entity_id=artifact.id, action="CRYPTO_VALIDATE_SUCCEEDED", after={"status": artifact.cryptographic_validation_status})
    except Exception:
        artifact.validation_error_count = int(artifact.validation_error_count or 0) + 1
        artifact.validation_last_checked_at = utils.now_utc()
        artifact.validation_last_result_source = source
        artifact.cryptographic_validation_status = models.CryptoValidationStatus.ERROR.value
        artifact.validation_summary_json = {"error": "validation_failed"}
        _provider_event(db, tenant_id=tenant_id, provider_name=provider.name, direction=models.ProviderDirection.ERROR.value, event_type=models.ProviderEventType.VALIDATE_FAILURE.value, artifact_id=artifact.id, request_id=req.id, payload={"error": "validation_failed"})
        _audit(db, amo_id=tenant_id, actor_user_id=None, entity_type="esign_artifact", entity_id=artifact.id, action="CRYPTO_VALIDATE_FAILED")


def _achieved_level(artifact: models.ESignSignedArtifact | None) -> str:
    if artifact is None:
        return models.SignaturePolicyLevel.BASIC_APPROVAL.value
    if artifact.cryptographic_signature_applied and artifact.timestamp_applied:
        return models.SignaturePolicyLevel.CRYPTO_AND_TIMESTAMP_REQUIRED.value
    if artifact.cryptographic_signature_applied:
        return models.SignaturePolicyLevel.CRYPTO_REQUIRED.value
    return models.SignaturePolicyLevel.APPEARANCE_ONLY_ALLOWED.value


def verify_and_sign_intent(db: Session, current_user: account_models.User, intent_id: str, credential: dict):
    intent = db.query(models.ESignSigningIntent).filter(models.ESignSigningIntent.id == intent_id, models.ESignSigningIntent.tenant_id == current_user.amo_id).first()
    if not intent:
        raise HTTPException(404, "Intent not found")
    signer = db.query(models.ESignSigner).filter(models.ESignSigner.id == intent.signer_id, models.ESignSigner.tenant_id == current_user.amo_id).first()
    req = db.query(models.ESignSignatureRequest).filter(models.ESignSignatureRequest.id == signer.signature_request_id, models.ESignSignatureRequest.tenant_id == current_user.amo_id).first()
    docv = db.query(models.ESignDocumentVersion).filter(models.ESignDocumentVersion.id == intent.doc_version_id, models.ESignDocumentVersion.tenant_id == current_user.amo_id).first()
    policy = db.query(models.ESignSignaturePolicy).filter(models.ESignSignaturePolicy.id == req.policy_id).first()

    assertion_verify(db, current_user, credential, intent_id=intent_id)

    if policy and policy.require_provider_health_before_finalization:
        h = get_signing_provider().healthcheck()
        if not h.get("ok") and not _active_override(db, req.id, current_user.amo_id, models.OverrideType.BYPASS_PROVIDER_HEALTHCHECK.value):
            _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_signature_request", entity_id=req.id, action="POLICY_BLOCKED_FALLBACK", after={"reason": "provider_health_failed"})
            db.commit()
            raise HTTPException(409, "Policy blocked finalization: provider not ready")

    src = Path(docv.storage_ref).read_bytes()
    provider = get_signing_provider()
    fallback_used = False
    downgrade_reason = None

    artifact = models.ESignSignedArtifact(
        tenant_id=current_user.amo_id,
        signature_request_id=req.id,
        doc_version_id=docv.id,
        storage_ref="",
        signed_content_sha256="",
        appearance_applied=False,
        cryptographic_signature_applied=False,
    )
    db.add(artifact)
    db.flush()

    try:
        token, token_raw, verify_url = _create_artifact_token(db, tenant_id=current_user.amo_id, artifact_id=artifact.id, actor_user_id=current_user.id)
    except Exception:
        _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_artifact", entity_id=artifact.id, action="VERIFY_QR_EMBED_FAILED", after={"reason": "token_creation_failed"})
        raise HTTPException(500, "Unable to create verification token")

    sign_ctx = {"placements": intent.payload_json.get("coordinates", []), "signer_name": signer.display_name or current_user.full_name, "approved_at": utils.now_utc().isoformat(), "doc_hash": docv.content_sha256, "verification_url": verify_url, "intent_hash": intent.intent_sha256, "signing_reason": _CFG.signing_reason_default, "signing_location": _CFG.signing_location_default}
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_artifact", entity_id=artifact.id, action="VERIFY_QR_EMBED_ATTEMPTED", after={"token_ref": _mask_token(token_raw)})

    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_signing_intent", entity_id=intent.id, action="CRYPTO_SIGN_ATTEMPTED")
    _provider_event(db, tenant_id=current_user.amo_id, provider_name=provider.name, direction=models.ProviderDirection.REQUEST.value, event_type=models.ProviderEventType.SIGN_ATTEMPT.value, request_id=req.id, artifact_id=artifact.id, payload={"intent_id": intent.id})

    try:
        sign_result = provider.sign_pdf(src, sign_ctx)
        if policy and policy.require_timestamp and not sign_result.timestamp_applied and not _active_override(db, req.id, current_user.amo_id, models.OverrideType.ACCEPT_NO_TIMESTAMP.value):
            raise RuntimeError("timestamp_required_not_met")
        if policy and policy.minimum_level in {models.SignaturePolicyLevel.CRYPTO_REQUIRED.value, models.SignaturePolicyLevel.CRYPTO_AND_TIMESTAMP_REQUIRED.value} and not sign_result.cryptographic_signature_applied:
            raise RuntimeError("crypto_required_not_met")
        _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_signing_intent", entity_id=intent.id, action="CRYPTO_SIGN_SUCCEEDED")
        _provider_event(db, tenant_id=current_user.amo_id, provider_name=provider.name, direction=models.ProviderDirection.RESPONSE.value, event_type=models.ProviderEventType.SIGN_SUCCESS.value, request_id=req.id, artifact_id=artifact.id, payload=sign_result.raw_provider_metadata)
        _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_artifact", entity_id=artifact.id, action="VERIFY_QR_EMBED_SUCCEEDED", after={"token_ref": _mask_token(token_raw)})
    except Exception:
        _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_signing_intent", entity_id=intent.id, action="CRYPTO_SIGN_FAILED")
        _provider_event(db, tenant_id=current_user.amo_id, provider_name=provider.name, direction=models.ProviderDirection.ERROR.value, event_type=models.ProviderEventType.SIGN_FAILURE.value, request_id=req.id, artifact_id=artifact.id, payload={"error": "sign_failed"})
        _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_artifact", entity_id=artifact.id, action="VERIFY_QR_EMBED_FAILED", after={"token_ref": _mask_token(token_raw), "reason": "provider_sign_failed"})
        allow_fallback = bool(policy.allow_fallback_to_appearance) if policy else True
        override = _active_override(db, req.id, current_user.amo_id, models.OverrideType.ALLOW_FALLBACK.value)
        if override:
            allow_fallback = True
            _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_override", entity_id=override.id, action="POLICY_OVERRIDE_USED")
        if not allow_fallback:
            _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_signature_request", entity_id=req.id, action="POLICY_BLOCKED_FALLBACK")
            raise HTTPException(409, "Policy blocked appearance fallback")
        fallback_used = True
        downgrade_reason = "CRYPTO_PROVIDER_FAILURE_FALLBACK"
        _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_signature_request", entity_id=req.id, action="PROVIDER_FALLBACK_TO_APPEARANCE_ONLY")
        sign_result = providers.AppearanceOnlyProvider().sign_pdf(src, sign_ctx)

    artifact.appearance_applied = sign_result.appearance_applied
    artifact.cryptographic_signature_applied = sign_result.cryptographic_signature_applied
    artifact.signing_provider = sign_result.signing_provider
    artifact.certificate_subject = sign_result.certificate_subject
    artifact.certificate_serial = sign_result.certificate_serial
    artifact.signing_time = sign_result.signing_time
    artifact.timestamp_applied = sign_result.timestamp_applied

    path = _artifact_path(current_user.amo_id, req.id, artifact.id)
    path.write_bytes(sign_result.output_pdf_bytes)
    artifact.storage_ref = str(path)
    artifact.signed_content_sha256 = utils.sha256_hex_bytes(path.read_bytes())
    if artifact.cryptographic_signature_applied:
        _validate_artifact_with_provider(db, artifact=artifact, req=req, tenant_id=current_user.amo_id)

    signer.status = models.SignerStatus.APPROVED.value
    signer.approved_at = utils.now_utc()
    intent.status = models.SigningIntentStatus.CONSUMED.value
    intent.consumed_at = utils.now_utc()

    req.finalized_with_fallback = fallback_used
    req.downgrade_reason_code = downgrade_reason
    req.achieved_level = _achieved_level(artifact)
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_signature_request", entity_id=req.id, action="SIGNATURE_POLICY_ACHIEVED", after={"achieved_level": req.achieved_level, "policy_compliant": _policy_compliant(policy, req.achieved_level)})

    pending = db.query(models.ESignSigner).filter(models.ESignSigner.signature_request_id == req.id, models.ESignSigner.tenant_id == current_user.amo_id, models.ESignSigner.status != models.SignerStatus.APPROVED.value).count()
    if pending == 0:
        req.status = models.SignatureRequestStatus.COMPLETED.value
        req.completed_at = utils.now_utc()
        _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_signature_request", entity_id=req.id, action="REQUEST_COMPLETED")

    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_signer", entity_id=signer.id, action="SIGNER_APPROVED", after={"intent_sha256": intent.intent_sha256})
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_artifact", entity_id=artifact.id, action="ARTIFACT_GENERATED", after={"signed_content_sha256": artifact.signed_content_sha256})
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_token", entity_id=token.id, action="TOKEN_CREATED")
    db.commit()
    return {"artifact_id": artifact.id, "verification_token": token_raw, "artifact_sha256": artifact.signed_content_sha256, "appearance_applied": artifact.appearance_applied, "cryptographic_signature_applied": artifact.cryptographic_signature_applied, "validation_status": artifact.cryptographic_validation_status}


def revoke_token(db: Session, current_user: account_models.User, token_id: str) -> None:
    token = db.query(models.ESignVerificationToken).filter(models.ESignVerificationToken.id == token_id, models.ESignVerificationToken.tenant_id == current_user.amo_id).first()
    if not token:
        raise HTTPException(404, "Not found")
    token.revoked_at = utils.now_utc()
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_token", entity_id=token.id, action="VERIFY_TOKEN_REVOKED")
    db.commit()


def _verify_payload(db: Session, token: str):
    t = db.query(models.ESignVerificationToken).filter(models.ESignVerificationToken.token == token).first()
    if not t or t.revoked_at is not None or _is_expired(t.expires_at):
        raise VerifyTokenNotFound
    artifact = db.query(models.ESignSignedArtifact).filter(models.ESignSignedArtifact.id == t.artifact_id, models.ESignSignedArtifact.tenant_id == t.tenant_id).first()
    req = db.query(models.ESignSignatureRequest).filter(models.ESignSignatureRequest.id == artifact.signature_request_id, models.ESignSignatureRequest.tenant_id == t.tenant_id).first()
    policy = db.query(models.ESignSignaturePolicy).filter(models.ESignSignaturePolicy.id == req.policy_id).first() if req.policy_id else None
    docv = db.query(models.ESignDocumentVersion).filter(models.ESignDocumentVersion.id == artifact.doc_version_id, models.ESignDocumentVersion.tenant_id == t.tenant_id).first()
    signers = db.query(models.ESignSigner).filter(models.ESignSigner.signature_request_id == req.id, models.ESignSigner.tenant_id == t.tenant_id).all()
    return t, artifact, req, policy, docv, signers


def verify_public_token(db: Session, token: str) -> schemas.VerifyOut:
    t, artifact, req, policy, docv, signers = _verify_payload(db, token)
    storage_valid = utils.sha256_hex_bytes(Path(artifact.storage_ref).read_bytes()) == artifact.signed_content_sha256

    if needs_revalidation(artifact, policy, utils.now_utc()):
        _audit(db, amo_id=t.tenant_id, actor_user_id=None, entity_type="esign_artifact", entity_id=artifact.id, action="POLICY_TRIGGERED_REVALIDATION")
        _validate_artifact_with_provider(db, artifact=artifact, req=req, tenant_id=t.tenant_id, source=models.ValidationResultSource.LIVE.value)
    else:
        artifact.validation_last_result_source = models.ValidationResultSource.CACHED.value
        _audit(db, amo_id=t.tenant_id, actor_user_id=None, entity_type="esign_artifact", entity_id=artifact.id, action="REVALIDATION_SKIPPED_CACHE_VALID")

    _audit(db, amo_id=t.tenant_id, actor_user_id=None, entity_type="esign_verify", entity_id=t.id, action="VERIFY_ENDPOINT_ACCESSED", after={"token_ref": _mask_token(token)})
    _audit(db, amo_id=t.tenant_id, actor_user_id=None, entity_type="esign_verify", entity_id=t.id, action="VERIFY_RESULT_RETURNED", after={"result": "VALID", "token_ref": _mask_token(token)})
    db.commit()

    return schemas.VerifyOut(
        valid=True,
        policy_code=policy.policy_code if policy else None,
        policy_minimum_level=policy.minimum_level if policy else None,
        achieved_level=req.achieved_level,
        policy_compliant=_policy_compliant(policy, req.achieved_level),
        finalized_with_fallback=req.finalized_with_fallback,
        downgrade_reason_code=req.downgrade_reason_code,
        storage_integrity_valid=storage_valid,
        signature_present=artifact.cryptographic_signature_applied,
        cryptographically_valid=artifact.cryptographic_validation_status == models.CryptoValidationStatus.VALID.value,
        timestamp_present=artifact.timestamp_applied,
        timestamp_valid=artifact.timestamp_valid,
        validation_status=artifact.cryptographic_validation_status,
        validation_last_checked_at=artifact.validation_last_checked_at,
        title=req.title,
        request_status=req.status,
        signers=[{"display_name": s.display_name, "email": _mask_email(s.email), "status": s.status, "approved_at": s.approved_at.isoformat() if s.approved_at else None} for s in signers],
        document_sha256=docv.content_sha256,
        artifact_sha256=artifact.signed_content_sha256,
        appearance_applied=artifact.appearance_applied,
        cryptographic_signature_applied=artifact.cryptographic_signature_applied,
    )


def get_artifact_validation(db: Session, current_user: account_models.User, artifact_id: str) -> schemas.ArtifactValidationOut:
    artifact = db.query(models.ESignSignedArtifact).filter(models.ESignSignedArtifact.id == artifact_id, models.ESignSignedArtifact.tenant_id == current_user.amo_id).first()
    if not artifact:
        raise HTTPException(404, "Not found")
    req = db.query(models.ESignSignatureRequest).filter(models.ESignSignatureRequest.id == artifact.signature_request_id, models.ESignSignatureRequest.tenant_id == current_user.amo_id).first()
    policy = db.query(models.ESignSignaturePolicy).filter(models.ESignSignaturePolicy.id == req.policy_id).first() if req.policy_id else None
    storage_valid = utils.sha256_hex_bytes(Path(artifact.storage_ref).read_bytes()) == artifact.signed_content_sha256
    return schemas.ArtifactValidationOut(
        artifact_id=artifact.id,
        policy_code=policy.policy_code if policy else None,
        policy_minimum_level=policy.minimum_level if policy else None,
        achieved_level=req.achieved_level,
        policy_compliant=_policy_compliant(policy, req.achieved_level),
        finalized_with_fallback=req.finalized_with_fallback,
        storage_integrity_valid=storage_valid,
        signature_present=artifact.cryptographic_signature_applied,
        cryptographically_valid=artifact.cryptographic_validation_status == models.CryptoValidationStatus.VALID.value,
        timestamp_present=artifact.timestamp_applied,
        timestamp_valid=artifact.timestamp_valid,
        cryptographic_validation_status=artifact.cryptographic_validation_status,
        certificate_subject=artifact.certificate_subject,
        certificate_serial=artifact.certificate_serial,
        signing_time=artifact.signing_time,
        validation_summary=artifact.validation_summary_json or {},
        validation_last_checked_at=artifact.validation_last_checked_at,
    )


def get_artifact_verify_link(db: Session, current_user: account_models.User, artifact_id: str) -> schemas.ArtifactVerifyLinkOut:
    artifact = db.query(models.ESignSignedArtifact).filter(models.ESignSignedArtifact.id == artifact_id, models.ESignSignedArtifact.tenant_id == current_user.amo_id).first()
    if not artifact:
        raise HTTPException(404, "Not found")
    token = db.query(models.ESignVerificationToken).filter(models.ESignVerificationToken.artifact_id == artifact.id, models.ESignVerificationToken.tenant_id == current_user.amo_id).order_by(models.ESignVerificationToken.created_at.desc()).first()
    if not token:
        raise HTTPException(404, "Not found")
    return schemas.ArtifactVerifyLinkOut(
        artifact_id=artifact.id,
        token_id=token.id,
        token_status="REVOKED" if token.revoked_at else ("EXPIRED" if _is_expired(token.expires_at) else "ACTIVE"),
        public_verify_url=build_public_verify_url(token.token),
        expires_at=token.expires_at,
        revoked_at=token.revoked_at,
        created_at=token.created_at,
    )


def regenerate_artifact_verify_link(db: Session, current_user: account_models.User, artifact_id: str) -> schemas.ArtifactVerifyLinkOut:
    artifact = db.query(models.ESignSignedArtifact).filter(models.ESignSignedArtifact.id == artifact_id, models.ESignSignedArtifact.tenant_id == current_user.amo_id).first()
    if not artifact:
        raise HTTPException(404, "Not found")
    old_tokens = db.query(models.ESignVerificationToken).filter(models.ESignVerificationToken.artifact_id == artifact.id, models.ESignVerificationToken.tenant_id == current_user.amo_id, models.ESignVerificationToken.revoked_at.is_(None)).all()
    now = utils.now_utc()
    for row in old_tokens:
        row.revoked_at = now
        _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_token", entity_id=row.id, action="VERIFY_TOKEN_REVOKED", after={"reason": "regenerated"})

    token, token_raw, _ = _create_artifact_token(db, tenant_id=current_user.amo_id, artifact_id=artifact.id, actor_user_id=current_user.id)
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_token", entity_id=token.id, action="VERIFY_LINK_REGENERATED", after={"artifact_id": artifact.id, "token_ref": _mask_token(token_raw)})
    db.commit()
    return schemas.ArtifactVerifyLinkOut(
        artifact_id=artifact.id,
        token_id=token.id,
        token_status="ACTIVE",
        public_verify_url=build_public_verify_url(token_raw),
        expires_at=token.expires_at,
        revoked_at=token.revoked_at,
        created_at=token.created_at,
    )


def revalidate_artifact(db: Session, current_user: account_models.User, artifact_id: str) -> schemas.ArtifactValidationOut:
    artifact = db.query(models.ESignSignedArtifact).filter(models.ESignSignedArtifact.id == artifact_id, models.ESignSignedArtifact.tenant_id == current_user.amo_id).first()
    if not artifact:
        raise HTTPException(404, "Not found")
    req = db.query(models.ESignSignatureRequest).filter(models.ESignSignatureRequest.id == artifact.signature_request_id, models.ESignSignatureRequest.tenant_id == current_user.amo_id).first()
    try:
        _validate_artifact_with_provider(db, artifact=artifact, req=req, tenant_id=current_user.amo_id, source=models.ValidationResultSource.LIVE.value)
    except Exception:
        _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_artifact", entity_id=artifact.id, action="REVALIDATION_FAILED")
    db.commit()
    return get_artifact_validation(db, current_user, artifact_id)



def _policy_for_request(db: Session, req: models.ESignSignatureRequest | None) -> models.ESignSignaturePolicy | None:
    if not req or not req.policy_id:
        return None
    return db.query(models.ESignSignaturePolicy).filter(models.ESignSignaturePolicy.id == req.policy_id).first()


def _policy_bool(policy: models.ESignSignaturePolicy | None, attr: str, default: bool) -> bool:
    return bool(getattr(policy, attr, default)) if policy is not None else default


def _artifact_and_request(db: Session, tenant_id: str, artifact_id: str):
    artifact = db.query(models.ESignSignedArtifact).filter(models.ESignSignedArtifact.id == artifact_id, models.ESignSignedArtifact.tenant_id == tenant_id).first()
    if not artifact:
        raise HTTPException(404, "Not found")
    req = db.query(models.ESignSignatureRequest).filter(models.ESignSignatureRequest.id == artifact.signature_request_id, models.ESignSignatureRequest.tenant_id == tenant_id).first()
    return artifact, req


def get_artifact_access(db: Session, current_user: account_models.User, artifact_id: str) -> schemas.ArtifactAccessOut:
    artifact, req = _artifact_and_request(db, current_user.amo_id, artifact_id)
    policy = _policy_for_request(db, req)
    size = Path(artifact.storage_ref).stat().st_size if Path(artifact.storage_ref).exists() else None
    return schemas.ArtifactAccessOut(
        artifact_available=True,
        preview_allowed=_policy_bool(policy, "allow_private_artifact_preview", True),
        download_allowed=_policy_bool(policy, "allow_private_artifact_download", True),
        public_preview_allowed=_policy_bool(policy, "allow_public_artifact_access", False),
        public_download_allowed=_policy_bool(policy, "allow_public_artifact_download", False),
        public_evidence_summary_allowed=_policy_bool(policy, "allow_public_evidence_summary_download", False),
        watermark_public_downloads=_policy_bool(policy, "watermark_public_downloads", True),
        require_auth_for_original_artifact=_policy_bool(policy, "require_auth_for_original_artifact", True),
        filename=Path(artifact.storage_ref).name,
        size_bytes=size,
    )


def private_artifact_path_for_preview(db: Session, current_user: account_models.User, artifact_id: str) -> str:
    artifact, req = _artifact_and_request(db, current_user.amo_id, artifact_id)
    policy = _policy_for_request(db, req)
    if not _policy_bool(policy, "allow_private_artifact_preview", True):
        raise HTTPException(403, "Preview not allowed")
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_artifact", entity_id=artifact.id, action="ARTIFACT_PREVIEWED")
    db.commit()
    return artifact.storage_ref


def private_artifact_path_for_download(db: Session, current_user: account_models.User, artifact_id: str) -> str:
    artifact, req = _artifact_and_request(db, current_user.amo_id, artifact_id)
    policy = _policy_for_request(db, req)
    if not _policy_bool(policy, "allow_private_artifact_download", True):
        raise HTTPException(403, "Download not allowed")
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_artifact", entity_id=artifact.id, action="ARTIFACT_DOWNLOADED")
    db.commit()
    return artifact.storage_ref


def public_artifact_access(db: Session, token: str) -> schemas.ArtifactAccessOut:
    t, artifact, req, policy, _docv, _signers = _verify_payload(db, token)
    return schemas.ArtifactAccessOut(
        artifact_available=True,
        preview_allowed=False,
        download_allowed=False,
        public_preview_allowed=_policy_bool(policy, "allow_public_artifact_access", False),
        public_download_allowed=_policy_bool(policy, "allow_public_artifact_download", False),
        public_evidence_summary_allowed=_policy_bool(policy, "allow_public_evidence_summary_download", False),
        watermark_public_downloads=_policy_bool(policy, "watermark_public_downloads", True),
        require_auth_for_original_artifact=_policy_bool(policy, "require_auth_for_original_artifact", True),
        filename=Path(artifact.storage_ref).name,
        size_bytes=Path(artifact.storage_ref).stat().st_size if Path(artifact.storage_ref).exists() else None,
    )


def public_artifact_download_path(db: Session, token: str) -> str:
    t, artifact, req, policy, _docv, _signers = _verify_payload(db, token)
    if not _policy_bool(policy, "allow_public_artifact_download", False):
        _audit(db, amo_id=t.tenant_id, actor_user_id=None, entity_type="esign_artifact", entity_id=artifact.id, action="PUBLIC_ARTIFACT_ACCESS_DENIED", after={"token_ref": _mask_token(token)})
        db.commit()
        raise HTTPException(403, "Artifact download not available")
    _audit(db, amo_id=t.tenant_id, actor_user_id=None, entity_type="esign_artifact", entity_id=artifact.id, action="PUBLIC_ARTIFACT_DOWNLOADED", after={"token_ref": _mask_token(token)})
    db.commit()
    return artifact.storage_ref


def public_evidence_summary_bytes(db: Session, token: str) -> bytes:
    t, artifact, req, policy, docv, signers = _verify_payload(db, token)
    if not _policy_bool(policy, "allow_public_evidence_summary_download", False):
        raise HTTPException(403, "Evidence summary not available")
    payload = {
        "title": req.title,
        "request_status": req.status,
        "document_sha256": docv.content_sha256,
        "artifact_sha256": artifact.signed_content_sha256,
        "appearance_applied": artifact.appearance_applied,
        "cryptographic_signature_applied": artifact.cryptographic_signature_applied,
        "signers": [{"display_name": s.display_name, "email": _mask_email(s.email), "approved_at": s.approved_at.isoformat() if s.approved_at else None} for s in signers],
    }
    _audit(db, amo_id=t.tenant_id, actor_user_id=None, entity_type="esign_evidence", entity_id=artifact.id, action="PUBLIC_EVIDENCE_SUMMARY_DOWNLOADED", after={"token_ref": _mask_token(token)})
    db.commit()
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _input_sha256(payload: schemas.HashCompareIn) -> str:
    if payload.provided_sha256:
        return payload.provided_sha256.strip().lower()
    if payload.file_base64:
        raw = base64.b64decode(payload.file_base64)
        return utils.sha256_hex_bytes(raw)
    raise HTTPException(400, "provided_sha256 or file_base64 required")


def compare_artifact_hash_private(db: Session, current_user: account_models.User, artifact_id: str, payload: schemas.HashCompareIn) -> schemas.HashCompareOut:
    artifact, req = _artifact_and_request(db, current_user.amo_id, artifact_id)
    docv = db.query(models.ESignDocumentVersion).filter(models.ESignDocumentVersion.id == artifact.doc_version_id, models.ESignDocumentVersion.tenant_id == current_user.amo_id).first()
    provided = _input_sha256(payload)
    against = payload.compare_against if payload.compare_against in {"artifact", "original"} else "artifact"
    expected = artifact.signed_content_sha256 if against == "artifact" else docv.content_sha256
    match = provided == (expected or "").lower()
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_artifact", entity_id=artifact.id, action="ARTIFACT_HASH_COMPARED", after={"against": against, "match": match})
    db.commit()
    return schemas.HashCompareOut(compared_against=against, provided_sha256=provided, expected_sha256=expected, match=match, message="Hash matches" if match else "Hash does not match")


def compare_artifact_hash_public(db: Session, token: str, payload: schemas.HashCompareIn) -> schemas.HashCompareOut:
    t, artifact, _req, _policy, _docv, _signers = _verify_payload(db, token)
    provided = _input_sha256(payload)
    expected = artifact.signed_content_sha256
    match = provided == (expected or "").lower()
    _audit(db, amo_id=t.tenant_id, actor_user_id=None, entity_type="esign_artifact", entity_id=artifact.id, action="PUBLIC_HASH_COMPARED", after={"token_ref": _mask_token(token), "match": match})
    db.commit()
    return schemas.HashCompareOut(compared_against="artifact", provided_sha256=provided, expected_sha256=expected, match=match, message="Hash matches" if match else "Hash does not match")

def provider_health(db: Session, current_user: account_models.User) -> schemas.ProviderHealthOut:
    provider = get_signing_provider()
    health = provider.healthcheck()
    _provider_event(db, tenant_id=current_user.amo_id, provider_name=provider.name, direction=models.ProviderDirection.RESPONSE.value, event_type=models.ProviderEventType.HEALTHCHECK.value, payload={"ok": bool(health.get("ok", False))})
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_provider", entity_id=provider.name, action="PROVIDER_HEALTHCHECK_RUN", after={"ok": bool(health.get("ok", False))})
    db.commit()
    return schemas.ProviderHealthOut(mode=_CFG.provider_mode, provider=provider.name, ok=bool(health.get("ok", False)), message=str(health.get("message", "ok")))


def provider_readiness(db: Session, current_user: account_models.User) -> schemas.ProviderReadinessOut:
    provider = get_signing_provider()
    health = provider.healthcheck()
    issues = []
    warnings = []
    health_ok = bool(health.get("ok", False))
    sign_ok = health_ok
    validate_ok = health_ok
    ts_capable = health.get("timestamp_capable") if isinstance(health, dict) else None
    if _CFG.provider_mode == "external_pades" and not health_ok:
        issues.append("provider_unreachable")
    if _CFG.provider_mode == "appearance":
        warnings.append("crypto_not_available_in_appearance_mode")
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_provider", entity_id=provider.name, action="PROVIDER_READINESS_CHECKED", after={"health_ok": health_ok})
    db.commit()
    return schemas.ProviderReadinessOut(configured_mode=_CFG.provider_mode, health_ok=health_ok, sign_endpoint_ok=sign_ok, validate_endpoint_ok=validate_ok, timestamp_capable=ts_capable, last_checked_at=utils.now_utc(), supports_appearance_only=True, supports_crypto_required=(_CFG.provider_mode == "external_pades" and health_ok), supports_crypto_timestamp_required=(_CFG.provider_mode == "external_pades" and health_ok and (ts_capable is not False)), blocking_issues=issues, warnings=warnings)


def create_override(db: Session, current_user: account_models.User, request_id: str, payload: schemas.PolicyOverrideIn) -> schemas.PolicyOverrideOut:
    req = db.query(models.ESignSignatureRequest).filter(models.ESignSignatureRequest.id == request_id, models.ESignSignatureRequest.tenant_id == current_user.amo_id).first()
    if not req:
        raise HTTPException(404, "Not found")
    row = models.ESignPolicyOverride(tenant_id=current_user.amo_id, request_id=req.id, override_type=payload.override_type, justification=payload.justification, approved_by_user_id=payload.approved_by_user_id or current_user.id, created_by_user_id=current_user.id, expires_at=payload.expires_at)
    db.add(row)
    db.flush()
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_override", entity_id=row.id, action="POLICY_OVERRIDE_CREATED", after={"override_type": row.override_type})
    db.commit()
    return schemas.PolicyOverrideOut(id=row.id, override_type=row.override_type, justification=row.justification, approved_by_user_id=row.approved_by_user_id, created_by_user_id=row.created_by_user_id, created_at=row.created_at, expires_at=row.expires_at, is_active=row.is_active)


def list_overrides(db: Session, current_user: account_models.User, request_id: str) -> list[schemas.PolicyOverrideOut]:
    rows = db.query(models.ESignPolicyOverride).filter(models.ESignPolicyOverride.request_id == request_id, models.ESignPolicyOverride.tenant_id == current_user.amo_id).order_by(models.ESignPolicyOverride.created_at.desc()).all()
    return [schemas.PolicyOverrideOut(id=r.id, override_type=r.override_type, justification=r.justification, approved_by_user_id=r.approved_by_user_id, created_by_user_id=r.created_by_user_id, created_at=r.created_at, expires_at=r.expires_at, is_active=r.is_active) for r in rows]


def create_evidence_bundle(db: Session, current_user: account_models.User, request_id: str) -> schemas.EvidenceBundleOut:
    req = db.query(models.ESignSignatureRequest).filter(models.ESignSignatureRequest.id == request_id, models.ESignSignatureRequest.tenant_id == current_user.amo_id).first()
    if not req:
        raise HTTPException(404, "Not found")
    policy = db.query(models.ESignSignaturePolicy).filter(models.ESignSignaturePolicy.id == req.policy_id).first() if req.policy_id else None
    artifact = db.query(models.ESignSignedArtifact).filter(models.ESignSignedArtifact.signature_request_id == req.id, models.ESignSignedArtifact.tenant_id == current_user.amo_id).order_by(models.ESignSignedArtifact.created_at.desc()).first()
    signers = db.query(models.ESignSigner).filter(models.ESignSigner.signature_request_id == req.id, models.ESignSigner.tenant_id == current_user.amo_id).all()
    intents = db.query(models.ESignSigningIntent).join(models.ESignSigner, models.ESignSigner.id == models.ESignSigningIntent.signer_id).filter(models.ESignSigningIntent.tenant_id == current_user.amo_id, models.ESignSigner.signature_request_id == req.id).all()
    events = db.query(models.ESignProviderEvent).filter(models.ESignProviderEvent.tenant_id == current_user.amo_id, models.ESignProviderEvent.request_id == req.id).all()

    manifest = {
        "request": {"id": req.id, "title": req.title, "status": req.status, "created_at": req.created_at.isoformat(), "completed_at": req.completed_at.isoformat() if req.completed_at else None},
        "policy": {"policy_code": policy.policy_code if policy else None, "minimum_level": policy.minimum_level if policy else None, "achieved_level": req.achieved_level, "policy_compliant": _policy_compliant(policy, req.achieved_level), "finalized_with_fallback": req.finalized_with_fallback, "downgrade_reason_code": req.downgrade_reason_code},
        "signers": [{"id": s.id, "display_name": s.display_name, "email": _mask_email(s.email), "status": s.status, "approved_at": s.approved_at.isoformat() if s.approved_at else None} for s in signers],
        "artifact": {"id": artifact.id if artifact else None, "artifact_sha256": artifact.signed_content_sha256 if artifact else None, "appearance_applied": bool(artifact and artifact.appearance_applied), "cryptographic_signature_applied": bool(artifact and artifact.cryptographic_signature_applied), "timestamp_applied": bool(artifact and artifact.timestamp_applied), "validation_status": artifact.cryptographic_validation_status if artifact else None},
        "webauthn_evidence": [{"intent_id": i.id, "intent_sha256": i.intent_sha256, "signer_id": i.signer_id} for i in intents],
        "provider_events": [{"provider": e.provider_name, "direction": e.direction, "event_type": e.event_type, "created_at": e.created_at.isoformat(), "payload": e.sanitized_payload_json} for e in events],
    }

    out_dir = utils.ensure_dir(_ESIGN_STORAGE / current_user.amo_id / req.id / "evidence")
    bundle_id = utils.random_token(12)
    bundle_path = out_dir / f"bundle_{bundle_id}.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        if artifact:
            zf.writestr("verification.json", json.dumps({"validation_summary": artifact.validation_summary_json or {}}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            zf.writestr("hashes.json", json.dumps({"artifact_sha256": artifact.signed_content_sha256}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            try:
                zf.write(artifact.storage_ref, arcname="signed-artifact.pdf")
            except Exception:
                pass

    sha = utils.sha256_hex_bytes(bundle_path.read_bytes())
    row = models.ESignEvidenceBundle(tenant_id=current_user.amo_id, request_id=req.id, artifact_id=artifact.id if artifact else None, storage_ref=str(bundle_path), bundle_sha256=sha, generated_at=utils.now_utc(), generated_by_user_id=current_user.id, format=models.EvidenceFormat.ZIP.value)
    db.add(row)
    db.flush()
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_evidence_bundle", entity_id=row.id, action="EVIDENCE_BUNDLE_GENERATED", after={"request_id": req.id})
    db.commit()
    return schemas.EvidenceBundleOut(bundle_id=row.id, request_id=req.id, artifact_id=row.artifact_id, bundle_sha256=row.bundle_sha256, generated_at=row.generated_at, format=row.format)


def get_evidence_bundle(db: Session, current_user: account_models.User, bundle_id: str) -> models.ESignEvidenceBundle:
    row = db.query(models.ESignEvidenceBundle).filter(models.ESignEvidenceBundle.id == bundle_id, models.ESignEvidenceBundle.tenant_id == current_user.amo_id).first()
    if not row:
        raise HTTPException(404, "Not found")
    return row


def trust_summary(db: Session, current_user: account_models.User, **filters) -> schemas.TrustSummaryOut:
    q = db.query(models.ESignSignatureRequest).filter(models.ESignSignatureRequest.tenant_id == current_user.amo_id)
    if filters.get("policy_code"):
        q = q.join(models.ESignSignaturePolicy, models.ESignSignaturePolicy.id == models.ESignSignatureRequest.policy_id).filter(models.ESignSignaturePolicy.policy_code == filters["policy_code"])
    rows = q.all()
    total = len(rows)
    completed = [r for r in rows if r.status == models.SignatureRequestStatus.COMPLETED.value]
    appearance = [r for r in completed if r.achieved_level == models.SignaturePolicyLevel.APPEARANCE_ONLY_ALLOWED.value]
    crypto = [r for r in completed if r.achieved_level in {models.SignaturePolicyLevel.CRYPTO_REQUIRED.value, models.SignaturePolicyLevel.CRYPTO_AND_TIMESTAMP_REQUIRED.value}]
    timestamped = [r for r in completed if r.achieved_level == models.SignaturePolicyLevel.CRYPTO_AND_TIMESTAMP_REQUIRED.value]
    fallback = [r for r in completed if r.finalized_with_fallback]
    violations = 0
    for r in completed:
        p = db.query(models.ESignSignaturePolicy).filter(models.ESignSignaturePolicy.id == r.policy_id).first() if r.policy_id else None
        if not _policy_compliant(p, r.achieved_level):
            violations += 1
    val_fail = db.query(models.ESignSignedArtifact).filter(models.ESignSignedArtifact.tenant_id == current_user.amo_id, models.ESignSignedArtifact.cryptographic_validation_status.in_([models.CryptoValidationStatus.INVALID.value, models.CryptoValidationStatus.ERROR.value])).count()
    _audit(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="esign_report", entity_id="trust_summary", action="TRUST_SUMMARY_VIEWED")
    db.commit()
    return schemas.TrustSummaryOut(total_requests=total, completed_requests=len(completed), appearance_only_completions=len(appearance), crypto_signed_completions=len(crypto), timestamped_completions=len(timestamped), fallback_count=len(fallback), policy_violation_count=violations, validation_failure_count=val_fail)
