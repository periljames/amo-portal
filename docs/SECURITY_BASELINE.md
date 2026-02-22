# SECURITY BASELINE

## 1) Threat model summary (confirmed-only)

Confirmed from repo:
- JWT bearer auth is used by backend security dependencies.
- Multi-tenant context exists via AMO/tenant identifiers in user/session flows.
- Public endpoints include auth + API + SSE stream (`/api/events`).
- Upload endpoints exist across multiple modules.

Primary threat categories:
1. **Tenant data leakage** from improper tenant scoping on reads/writes.
2. **Credential/session abuse** (token theft, weak secrets, missing revocation enforcement).
3. **Upload abuse** (oversized payloads, malware/polyglot uploads, storage exhaustion).
4. **Realtime abuse** (unauthorized stream subscription, replay abuse, resource exhaustion).
5. **Edge exposure risk** if internal/admin surfaces are internet-accessible.

`UNKNOWN__FILL_ME`: formal tenant isolation contract from `portal_spec.md`.

## 2) Hardening checklist

### Auth/session/cookies
- Enforce strong `SECRET_KEY` via secret store (`PLACEHOLDER__SET_IN_SECRET_STORE`).
- Keep access token TTL explicit (`ACCESS_TOKEN_EXPIRE_MINUTES`) and short-lived for high-risk roles (`ASSUMPTION__REVIEW`).
- Ensure token revocation checks remain enabled (already implemented in backend).
- If cookies are used later: `Secure`, `HttpOnly`, `SameSite=Lax/Strict`, rotation on privilege change.

### HTTP headers (EDGE)
- `Strict-Transport-Security` with preload only after stable HTTPS.
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- CSP baseline in nginx snippet (`ASSUMPTION__REVIEW` to tune per frontend assets).

### Rate/connection limiting
- Apply token bucket to `/auth/*` and API routes.
- Stricter per-IP limits on upload and stream endpoints.
- Connection caps on `/api/events` to prevent SSE fan-out abuse.

### Upload controls
- Explicit `client_max_body_size` and backend size checks.
- Content-type allowlists and file extension normalization.
- Quarantine/scanning pipeline `UNKNOWN__FILL_ME`.

## 3) Secrets and least privilege policy

- No secrets in Git, Dockerfiles, or committed `.env`.
- All secret values sourced from external secret store and injected at deploy time.
- Separate DB users:
  - app runtime user (least privilege DML)
  - migration user (DDL)
- SSH admin restricted to management network only.
- Database not internet-accessible.

## 4) Logging and audit baseline

- Preserve auth events (login success/fail, token revocation, role changes).
- Preserve tenant-scoped audit records for data mutations.
- Keep EDGE access logs with request ID and upstream status.
- Retention period `UNKNOWN__FILL_ME` days.
- Forward logs to central sink `UNKNOWN__FILL_ME` (Loki/ELK/etc.).

## 5) Access boundaries

- Public: EDGE `443` only.
- Internal only: APP service ports, DB `5432`, admin dashboards for infra tools.
- Optional NC/JF admin surfaces restricted by VPN or management ACLs.
- Broker internal ports not public; only websocket entry via EDGE path if required.

## 6) Rollback and security response

- If a release introduces security regression:
  1. `./scripts/rollback.sh`
  2. Rotate compromised secrets.
  3. Revoke active tokens (set user `token_revoked_at` strategy).
  4. Review logs for blast radius and notify stakeholders.
