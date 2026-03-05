from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user

from . import schemas, services

router = APIRouter(prefix="/api/v1/esign", tags=["esign"], dependencies=[Depends(require_module("ESIGN_MODULE"))])


def _require_admin(current_user: account_models.User) -> None:
    role = getattr(current_user.role, "value", str(current_user.role))
    if not (current_user.is_superuser or role in {"AMO_ADMIN", "SUPERUSER"}):
        raise HTTPException(status_code=403, detail="Admin privileges required")


@router.post("/webauthn/registration/options", response_model=schemas.PublicKeyOptionsOut)
def webauthn_registration_options(payload: schemas.RegistrationOptionsIn, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    services.enforce_rate_limit(request, current_user.amo_id, "webauthn_registration_options")
    return schemas.PublicKeyOptionsOut(options=services.registration_options(db, current_user, payload).model_dump())


@router.post("/webauthn/registration/verify")
def webauthn_registration_verify(payload: schemas.WebAuthnRegistrationVerifyIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    cred = services.registration_verify(db, current_user, payload.credential)
    return {"credential_id": cred.id, "sign_count": cred.sign_count}


@router.post("/webauthn/assertion/options", response_model=schemas.PublicKeyOptionsOut)
def webauthn_assertion_options(payload: schemas.WebAuthnAssertionOptionsIn, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    services.enforce_rate_limit(request, current_user.amo_id, "webauthn_assertion_options")
    return schemas.PublicKeyOptionsOut(options=services.assertion_options(db, current_user, payload.intent_id).model_dump())


@router.post("/webauthn/assertion/verify")
def webauthn_assertion_verify(payload: schemas.WebAuthnAssertionVerifyIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    cred = services.assertion_verify(db, current_user, payload.credential)
    return {"credential_id": cred.id, "sign_count": cred.sign_count}




@router.get("/webauthn/credentials", response_model=list[schemas.WebAuthnCredentialOut])
def webauthn_credentials(db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    return services.list_webauthn_credentials(db, current_user)


@router.delete("/webauthn/credentials/{credential_id}")
def delete_webauthn_credential(credential_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    services.deactivate_webauthn_credential(db, current_user, credential_id)
    return {"status": "removed"}



@router.patch("/webauthn/credentials/{credential_id}", response_model=schemas.WebAuthnCredentialOut)
def patch_webauthn_credential(credential_id: str, payload: schemas.WebAuthnCredentialPatchIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    row = services.rename_webauthn_credential(db, current_user, credential_id, payload.nickname)
    return services._serialize_webauthn_credential(row)


@router.get("/inbox", response_model=schemas.InboxOut)
def esign_inbox(
    status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return services.list_signing_inbox(db, current_user, status=status, date_from=date_from, date_to=date_to, page=page, page_size=page_size)


@router.get("/inbox/count", response_model=schemas.InboxCountOut)
def esign_inbox_count(db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    return services.inbox_count(db, current_user)

@router.post("/requests", response_model=schemas.RequestCreateOut)
def create_request(payload: schemas.RequestCreateIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    return services.create_signature_request(db, current_user, payload)


@router.post("/requests/{request_id}/send", response_model=schemas.SendRequestOut)
def send_request(request_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    req = services.send_request(db, current_user, request_id)
    return schemas.SendRequestOut(id=req.id, status=req.status, sent_at=req.sent_at)


@router.get("/requests/{request_id}/signing-context", response_model=schemas.SigningContextOut)
def signing_context(request_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    return services.get_signing_context(db, current_user, request_id)


@router.post("/requests/{request_id}/evidence-bundle", response_model=schemas.EvidenceBundleOut)
def generate_evidence_bundle(request_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    return services.create_evidence_bundle(db, current_user, request_id)


@router.get("/evidence-bundles/{bundle_id}", response_model=schemas.EvidenceBundleOut)
def get_evidence_bundle(bundle_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    row = services.get_evidence_bundle(db, current_user, bundle_id)
    return schemas.EvidenceBundleOut(bundle_id=row.id, request_id=row.request_id, artifact_id=row.artifact_id, bundle_sha256=row.bundle_sha256, generated_at=row.generated_at, format=row.format)


@router.get("/evidence-bundles/{bundle_id}/download")
def download_evidence_bundle(bundle_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    row = services.get_evidence_bundle(db, current_user, bundle_id)
    return FileResponse(row.storage_ref, media_type="application/zip", filename=f"esign_evidence_{bundle_id}.zip")


@router.post("/requests/{request_id}/overrides", response_model=schemas.PolicyOverrideOut)
def create_override(request_id: str, payload: schemas.PolicyOverrideIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    _require_admin(current_user)
    return services.create_override(db, current_user, request_id, payload)


@router.get("/requests/{request_id}/overrides", response_model=list[schemas.PolicyOverrideOut])
def list_overrides(request_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    _require_admin(current_user)
    return services.list_overrides(db, current_user, request_id)


@router.post("/intents/{intent_id}/assertion/options", response_model=schemas.PublicKeyOptionsOut)
def intent_assertion_options(intent_id: str, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    services.enforce_rate_limit(request, current_user.amo_id, "intent_assertion_options")
    return schemas.PublicKeyOptionsOut(options=services.assertion_options(db, current_user, intent_id).model_dump())


@router.post("/intents/{intent_id}/assertion/verify-and-sign")
def verify_and_sign(intent_id: str, payload: schemas.WebAuthnAssertionVerifyIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    return services.verify_and_sign_intent(db, current_user, intent_id, payload.credential)


@router.post("/tokens/{token_id}/revoke")
def revoke_token(token_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    services.revoke_token(db, current_user, token_id)
    return {"status": "revoked"}




@router.get("/artifacts/{artifact_id}/access", response_model=schemas.ArtifactAccessOut)
def artifact_access(artifact_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    return services.get_artifact_access(db, current_user, artifact_id)


@router.get("/artifacts/{artifact_id}/preview")
def artifact_preview(artifact_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    path = services.private_artifact_path_for_preview(db, current_user, artifact_id)
    return FileResponse(path, media_type="application/pdf", filename="signed-artifact.pdf")


@router.get("/artifacts/{artifact_id}/download")
def artifact_download(artifact_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    path = services.private_artifact_path_for_download(db, current_user, artifact_id)
    return FileResponse(path, media_type="application/pdf", filename="signed-artifact.pdf")


@router.post("/artifacts/{artifact_id}/compare-hash", response_model=schemas.HashCompareOut)
def artifact_compare_hash(artifact_id: str, payload: schemas.HashCompareIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    return services.compare_artifact_hash_private(db, current_user, artifact_id, payload)

@router.get("/artifacts/{artifact_id}/validation", response_model=schemas.ArtifactValidationOut)
def artifact_validation(artifact_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    return services.get_artifact_validation(db, current_user, artifact_id)


@router.post("/artifacts/{artifact_id}/revalidate", response_model=schemas.ArtifactValidationOut)
def artifact_revalidate(artifact_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    return services.revalidate_artifact(db, current_user, artifact_id)


@router.post("/artifacts/{artifact_id}/revalidate-now", response_model=schemas.ArtifactValidationOut)
def artifact_revalidate_now(artifact_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    return services.revalidate_artifact(db, current_user, artifact_id)


@router.get("/artifacts/{artifact_id}/verify-link", response_model=schemas.ArtifactVerifyLinkOut)
def artifact_verify_link(artifact_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    _require_admin(current_user)
    return services.get_artifact_verify_link(db, current_user, artifact_id)


@router.post("/artifacts/{artifact_id}/verify-link/regenerate", response_model=schemas.ArtifactVerifyLinkOut)
def artifact_verify_link_regenerate(artifact_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    _require_admin(current_user)
    return services.regenerate_artifact_verify_link(db, current_user, artifact_id)


@router.get("/provider/health", response_model=schemas.ProviderHealthOut)
def provider_health(db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    _require_admin(current_user)
    return services.provider_health(db, current_user)


@router.get("/provider/readiness", response_model=schemas.ProviderReadinessOut)
def provider_readiness(db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    _require_admin(current_user)
    return services.provider_readiness(db, current_user)


@router.get("/reports/trust-summary", response_model=schemas.TrustSummaryOut)
def trust_summary(
    date_start: str | None = None,
    date_end: str | None = None,
    policy_code: str | None = None,
    achieved_level: str | None = None,
    policy_compliant: bool | None = None,
    finalized_with_fallback: bool | None = None,
    provider_mode: str | None = None,
    signer_type: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_admin(current_user)
    return services.trust_summary(db, current_user, date_start=date_start, date_end=date_end, policy_code=policy_code, achieved_level=achieved_level, policy_compliant=policy_compliant, finalized_with_fallback=finalized_with_fallback, provider_mode=provider_mode, signer_type=signer_type)


public_router = APIRouter(prefix="/api/v1/esign", tags=["esign_public"])


@public_router.get("/verify/{token}", response_model=schemas.VerifyOut)
def verify_token(token: str, db: Session = Depends(get_db)):
    try:
        return services.verify_public_token(db, token)
    except services.VerifyTokenNotFound:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception:
        raise HTTPException(status_code=503, detail="Verification unavailable")


@public_router.get("/verify/{token}.json", response_model=schemas.VerifyOut)
def verify_token_json(token: str, db: Session = Depends(get_db)):
    try:
        return services.verify_public_token(db, token)
    except services.VerifyTokenNotFound:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception:
        raise HTTPException(status_code=503, detail="Verification unavailable")


@public_router.get("/verify/{token}/artifact-access", response_model=schemas.ArtifactAccessOut)
def verify_token_artifact_access(token: str, db: Session = Depends(get_db)):
    try:
        return services.public_artifact_access(db, token)
    except services.VerifyTokenNotFound:
        raise HTTPException(status_code=404, detail="Not found")


@public_router.get("/verify/{token}/download")
def verify_token_download(token: str, db: Session = Depends(get_db)):
    try:
        path = services.public_artifact_download_path(db, token)
        return FileResponse(path, media_type="application/pdf", filename="verified-artifact.pdf")
    except services.VerifyTokenNotFound:
        raise HTTPException(status_code=404, detail="Not found")


@public_router.get("/verify/{token}/evidence-summary")
def verify_token_evidence_summary(token: str, db: Session = Depends(get_db)):
    try:
        content = services.public_evidence_summary_bytes(db, token)
        return Response(content=content, media_type="application/json")
    except services.VerifyTokenNotFound:
        raise HTTPException(status_code=404, detail="Not found")


@public_router.post("/verify/{token}/compare-hash", response_model=schemas.HashCompareOut)
def verify_token_compare_hash(token: str, payload: schemas.HashCompareIn, db: Session = Depends(get_db)):
    try:
        return services.compare_artifact_hash_public(db, token, payload)
    except services.VerifyTokenNotFound:
        raise HTTPException(status_code=404, detail="Not found")
