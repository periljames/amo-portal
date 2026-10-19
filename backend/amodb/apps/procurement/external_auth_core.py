"""External identities are NOT internal User principals and never receive staff JWTs.

Use existing Argon2id password hashes, shared auth limiter and transaction-local
tenant context; authenticate every operation against persistent revoked sessions.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi import HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.apps.accounts import auth_rate_limit, services
from amodb.apps.quality.tenant_security import set_postgres_tenant_context
from amodb.security import SECRET_KEY, get_password_hash, verify_password

COOKIE = "amo_external_session"
SESSION_HOURS = 8
CAPABILITIES = frozenset({
    "profile.read", "document.read", "document.submit", "capa.respond",
    "task.read", "task.respond", "contract.read", "contract.acknowledge",
    "profile.propose", "members.read", "procurement.read", "procurement.respond", "procurement.attach",
    "members.manage", "sessions.manage",
})
ROLE_CAPS = {
    "PROVIDER_ADMIN": CAPABILITIES,
    "QUALITY_REPRESENTATIVE": frozenset({"profile.read","profile.propose","document.read","document.submit","capa.respond","task.read","task.respond","members.read","sessions.manage","procurement.read","procurement.attach"}),
    "TECHNICAL_REPRESENTATIVE": frozenset({"profile.read","profile.propose","document.read","document.submit","capa.respond","task.read","task.respond","sessions.manage","procurement.read","procurement.attach"}),
    "COMMERCIAL_REPRESENTATIVE": frozenset({"profile.read","profile.propose","document.read","contract.read","contract.acknowledge","task.read","sessions.manage","procurement.read","procurement.respond","procurement.attach","document.submit"}),
    "DOCUMENT_SUBMITTER": frozenset({"profile.read","document.read","document.submit","task.read","sessions.manage","procurement.read","procurement.attach"}),
    "READ_ONLY": frozenset({"profile.read","document.read","task.read","sessions.manage","procurement.read"}),
}
APP_ENV = (os.getenv("APP_ENV") or os.getenv("ENV") or "development").lower()
SECURE = APP_ENV in {"production", "prod"}
COOKIE_PATH = "/api/external-provider"
MAX_AGE = SESSION_HOURS * 3600

def now():
    return datetime.now(timezone.utc)

def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value

def new_id():
    return str(uuid4())

def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def one(query, db, **kwargs):
    return db.execute(text(query), kwargs).mappings().first()

def many(query, db, **kwargs):
    return [dict(row) for row in db.execute(text(query), kwargs).mappings().all()]

def run(query, db, **kwargs):
    return db.execute(text(query), kwargs)

def tenant(db: Session, slug: str):
    amo = one("""SELECT id, login_slug, is_active FROM amos
        WHERE lower(login_slug)=lower(:slug) OR lower(amo_code)=lower(:slug)""",db,slug=slug)
    if not amo or not amo["is_active"]:
        raise HTTPException(404,"Tenant not available")
    return str(amo["id"])

def context(db: Session, amo_id: str, actor: str = ""):
    set_postgres_tenant_context(db, amo_id=amo_id, user_id=actor)

def require_csrf(request: Request, expected_hash: str):
    origin = request.headers.get("origin") or request.headers.get("referer")
    # The browser always supplies an Origin for cross-origin-sensitive writes.
    if origin:
        from urllib.parse import urlparse
        parsed = urlparse(origin)
        if parsed.scheme not in {"http","https"} or parsed.netloc != request.url.netloc:
            raise HTTPException(403,"Cross-origin provider operation denied")
    elif request.headers.get("sec-fetch-site") not in {"same-origin", "none"}:
        raise HTTPException(403,"Same-origin verification required")
    value = request.headers.get("x-external-csrf", "")
    if not value or not hmac.compare_digest(digest(value), expected_hash):
        raise HTTPException(403,"Provider CSRF token missing or invalid")

def cookie(response: Response, raw: str | None):
    if raw:
        response.set_cookie(COOKIE, raw, httponly=True, secure=SECURE,
                            samesite="strict", path=COOKIE_PATH, max_age=MAX_AGE)
    else:
        response.delete_cookie(COOKIE, httponly=True, secure=SECURE,
                               samesite="strict", path=COOKIE_PATH)

def token(db, *, tenant_id: str, grant_id: str, identity_id: str, kind: str, hours: int):
    raw = f"{tenant_id}.{secrets.token_urlsafe(40)}"
    run("""INSERT INTO external_identity_tokens
        (id,amo_id,identity_id,grant_id,kind,token_hash,expires_at)
        VALUES (:id,:amo,:person,:grant,:kind,:hash,:expires)""",
        db,id=new_id(),amo=tenant_id,person=identity_id,grant=grant_id,
        kind=kind,hash=digest(raw),expires=now()+timedelta(hours=hours))
    return raw

def redeem_token(db, raw: str, kind: str):
    # Transaction is locked around redemption; a consumed code cannot be replayed.
    tenant_hint, separator, _ = raw.partition(".")
    if not separator or len(tenant_hint) != 36:
        raise HTTPException(400,"Invalid or expired verification code")
    context(db,tenant_hint)
    row=one("""SELECT tok.*, amo.is_active AS tenant_active
        FROM external_identity_tokens tok
        JOIN amos amo ON amo.id=tok.amo_id
        WHERE tok.amo_id=:amo AND tok.token_hash=:hash AND tok.kind=:kind
        FOR UPDATE OF tok""",db,amo=tenant_hint,hash=digest(raw),kind=kind)
    if not row or row["used_at"] or row["revoked_at"] or aware(row["expires_at"]) <= now():
        raise HTTPException(400,"Invalid or expired verification code")
    context(db,str(row["amo_id"]),str(row["identity_id"]))
    if row["tenant_active"] is not True:
        raise HTTPException(403,"The parent AMO tenant is suspended")
    run("UPDATE external_identity_tokens SET used_at=:at WHERE id=:id",db,at=now(),id=row["id"])
    return row

def event(db, *, amo: str, identity: str | None, grant: str | None, action: str,
          actor_user: str | None = None, actor_identity: str | None = None, details=None):
    # Never write credentials, access tokens, verification codes or TOTP seeds.
    run("""INSERT INTO external_security_events
        (id,amo_id,identity_id,grant_id,actor_identity_id,actor_user_id,event_type,details_json)
        VALUES (:id,:amo,:identity,:grant,:actor_identity,:actor_user,:action,CAST(:details AS JSON))""",
        db,id=new_id(),amo=amo,identity=identity,grant=grant,actor_identity=actor_identity,
        actor_user=actor_user,action=action,details=__import__("json").dumps(details or {}))

def issue_session(db, response, *, amo: str, identity: str, grant: str, request: Request, mfa: bool = False):
    raw=f"{amo}.{secrets.token_urlsafe(48)}"
    csrf=secrets.token_urlsafe(32)
    ident=one("SELECT password_version FROM external_credentials WHERE identity_id=:id",db,id=identity)
    if ident is None:
        raise HTTPException(409,"Credentials not enrolled")
    sid=new_id()
    run("""INSERT INTO external_sessions
        (id,amo_id,identity_id,grant_id,session_hash,csrf_hash,expires_at,mfa_verified_at,ip_hash,user_agent_hash)
        VALUES (:id,:amo,:identity,:grant,:hash,:csrf,:expires,:mfa,:ip,:ua)""", db,
        id=sid,amo=amo,identity=identity,grant=grant,hash=digest(raw),csrf=digest(csrf),
        expires=now()+timedelta(hours=SESSION_HOURS),mfa=now() if mfa else None,
        ip=digest(request.client.host) if request.client else None,
        ua=digest(request.headers.get("user-agent","")) if request.headers.get("user-agent") else None)
    cookie(response,raw)
    event(db,amo=amo,identity=identity,grant=grant,action="LOGIN",actor_identity=identity)
    return csrf

def active_session(db: Session, request: Request, required: str | None = None, write=False):
    raw=request.cookies.get(COOKIE)
    if not raw:
        raise HTTPException(401,"Provider login required")
    tenant_hint, separator, _ = raw.partition(".")
    if not separator or len(tenant_hint) != 36:
        raise HTTPException(401,"Provider session invalid")
    context(db,tenant_hint)
    row=one("""SELECT s.*, g.status grant_state, g.role_code, g.capabilities_json,
          g.object_scope_json, g.tenant_provider_id, p.portal_state, p.restrict_new_work,
          p.organization_id, p.supplier_id, m.status membership_state,
          i.status identity_state, i.verified_at, c.locked_until,
          supplier.status supplier_lifecycle, supplier.is_active supplier_active,
          supplier.external_import_pending_activation import_pending,
          amo.is_active tenant_active
        FROM external_sessions s
        JOIN amos amo ON amo.id=s.amo_id
        JOIN external_tenant_grants g ON g.id=s.grant_id AND g.amo_id=s.amo_id
        JOIN external_tenant_providers p ON p.id=g.tenant_provider_id AND p.amo_id=s.amo_id
        JOIN external_organization_memberships m ON m.id=g.membership_id AND m.identity_id=s.identity_id AND m.organization_id=p.organization_id
        JOIN external_identities i ON i.id=s.identity_id
        JOIN external_credentials c ON c.identity_id=i.id
        JOIN procurement_suppliers supplier
          ON supplier.amo_id=p.amo_id AND supplier.id=p.supplier_id
        WHERE s.amo_id=:amo AND s.session_hash=:hash""",db,amo=tenant_hint,hash=digest(raw))
    if not row:
        raise HTTPException(401,"Provider session invalid")
    context(db,str(row["amo_id"]),str(row["identity_id"]))
    # An existing vendor cookie must lose all authority immediately if its
    # parent AMO tenant is suspended, including historical document reads,
    # profile changes, and previously delegated corrective-action access.
    if row["tenant_active"] is not True:
        raise HTTPException(403,"Parent AMO tenant is suspended")
    if row["revoked_at"] or aware(row["expires_at"])<=now() or row["identity_state"]!="ACTIVE" or not row["verified_at"] or row["grant_state"]!="ACTIVE" or row["membership_state"]!="ACTIVE" or (row["locked_until"] and aware(row["locked_until"])>now()):
        raise HTTPException(401,"Provider account or session revoked")
    if row["portal_state"]!="ACTIVE":
        if row["portal_state"]!="SUSPENDED" or required not in {None,"capa.respond","profile.read","profile.propose","sessions.manage","document.read","procurement.read"}:
            raise HTTPException(403,"Provider portal access suspended")
    caps=set(row["capabilities_json"] or [])
    if required and (required not in caps or required not in CAPABILITIES):
        raise HTTPException(403,"Provider capability not granted")
    # A portal account is independent of procurement and Quality approval.
    # Authentication does not authorize work while the canonical supplier is
    # prospective, unapproved, expired, inactive or suspended.
    supplier_state=str(row["supplier_lifecycle"] or "")
    if "." in supplier_state:
        supplier_state=supplier_state.rsplit(".",1)[-1]
    supplier_eligible=(
        bool(row["supplier_active"])
        and not bool(row["import_pending"])
        and supplier_state in {"APPROVED","CONDITIONALLY_APPROVED"}
    )
    if (row["restrict_new_work"] or not supplier_eligible) and required not in {
        None,"capa.respond","profile.read","profile.propose","sessions.manage",
        "document.read","document.submit","procurement.read"
    }:
        raise HTTPException(403,"Provider is restricted to account control and existing corrective actions")
    if write:
        require_csrf(request,row["csrf_hash"])
    return row

def scope_allows(session, *, contract_id=None, document_id=None, assignment_id=None):
    scope=session["object_scope_json"] or {}
    for key, value in (("contracts",contract_id),("documents",document_id),("assignments",assignment_id)):
        if value is not None and str(value) not in [str(v) for v in scope.get(key,[])]:
            raise HTTPException(403,f"Provider {key} access not assigned")
    return True


def revoke_identity_sessions(db: Session, identity_id: str, except_session_id: str | None = None):
    """Revoke every tenant session even with FORCE RLS on session rows."""
    tenants=db.execute(text("SELECT id FROM amos")).scalars().all()
    total=0
    for tenant_id in tenants:
        context(db,str(tenant_id),identity_id)
        result=run("""UPDATE external_sessions SET revoked_at=:at
            WHERE amo_id=:amo AND identity_id=:identity AND revoked_at IS NULL
            AND (:except_id IS NULL OR id<>:except_id)""",
            db,at=now(),amo=str(tenant_id),identity=identity_id,except_id=except_session_id)
        total+=result.rowcount
    return total

def consume_other_reset_tokens(db: Session, identity_id: str):
    """A successful password operation invalidates pending recovery codes from
    every tenant sharing this identity, respecting FORCE RLS."""
    tenants=db.execute(text("SELECT id FROM amos")).scalars().all()
    for tenant_id in tenants:
        context(db,str(tenant_id),identity_id)
        run("""UPDATE external_identity_tokens SET revoked_at=:at
          WHERE amo_id=:amo AND identity_id=:identity
          AND kind='RESET' AND used_at IS NULL AND revoked_at IS NULL""",db,
          at=now(),amo=str(tenant_id),identity=identity_id)


def require_recent_mfa(db: Session, session, minutes: int = 15):
    credential=one("SELECT totp_confirmed_at FROM external_credentials WHERE identity_id=:id",
                    db,id=session["identity_id"])
    passkey=one("""SELECT id FROM external_passkey_credentials
        WHERE identity_id=:id AND is_active=true LIMIT 1""",db,id=session["identity_id"])
    if not (credential and credential["totp_confirmed_at"]) and not passkey:
        raise HTTPException(403,"Enroll and verify MFA or a passkey before this sensitive provider action")
    if not session["mfa_verified_at"] or (now()-aware(session["mfa_verified_at"])).total_seconds()>minutes*60:
        raise HTTPException(403,"Recent second-factor verification required")


def password_is_valid(value):
    try:
        services._validate_password_strength(value)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc

def secret_box():
    # Derived from the existing application secret. Cryptography, not raw DB
    # storage, protects the TOTP seed at rest.
    key=hashlib.sha256(("external-totp-v1:"+SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))

def totp_valid(encrypted: str, code: str) -> bool:
    try:
        secret=base64.b32decode(secret_box().decrypt(encrypted.encode()),casefold=True)
        step=int(time.time()//30)
        for tick in (step-1,step,step+1):
            payload=hmac.new(secret,tick.to_bytes(8,"big"),hashlib.sha1).digest()
            offset=payload[-1]&15
            value=int.from_bytes(payload[offset:offset+4],"big")&0x7fffffff
            if hmac.compare_digest(f"{value%1000000:06d}",code):
                return True
    except Exception:
        return False
    return False

def auth_limit(request, email: str, endpoint: str):
    address=request.client.host if request.client else "unknown"
    auth_rate_limit.enforce(address,f"external-ip-{endpoint}",limit=120)
    auth_rate_limit.enforce(email.casefold(),f"external-identity-{endpoint}",limit=10)
