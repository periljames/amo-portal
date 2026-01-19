# AMO Portal – Security Report (Initial Sweep)

| Severity | Area | Issue | Recommendation | Status / Verification |
| --- | --- | --- | --- | --- |
| High | CORS | CORS allowed `*` with credentials enabled in `amodb.main`. | Make origins env-driven and disallow credentials when wildcard is used. | **Addressed** in this commit (`CORS_ALLOWED_ORIGINS` parsing; defaults to localhost) via code review. |
| High | Secrets | `SECRET_KEY` in `security.py` falls back to `CHANGE_ME_IN_PRODUCTION`. | Require `SECRET_KEY` env in production builds; add startup guard or env validation. | Open. Verified by reading `amodb/security.py`. |
| High | Auth endpoints | No rate limiting or brute-force protection on `/auth/login` and password reset routes. | Introduce rate limiting (e.g., slowapi/Redis) and IP/user lockouts; log/alert suspicious attempts. | Open. Observed in `apps/accounts/router_public.py`. |
| Medium | File uploads | AMO asset upload paths/validation not enforced (metadata stored only). Risk of oversized or unsafe uploads. | Add MIME/extension allowlist, size caps, randomised storage paths outside web root, and optional AV scan hook. | Open. Observed in `apps/accounts` asset handling. |
| Medium | RBAC coverage | Role dependencies exist but not uniformly applied across all routers (fleet/work/quality). | Audit routers, wrap sensitive routes with `require_roles`/`require_admin`, and add tests. | Open. Spot-checked routers under `amodb/apps`. |
| Medium | Dependency hygiene | No documented npm/pip audit results; versions may be stale. | Run `pip list --outdated`/`npm audit`, patch criticals, pin versions. | Open. No audit artifacts present. |
| Low | Logging privacy | Authentication services capture IP/User-Agent for audit, but broader request logging settings are unclear. | Ensure sensitive tokens/passwords are not logged and add redaction filters if enabling structured logs. | Open. Requires log config review. |

Next actions should prioritise secrets enforcement, auth rate limiting, and upload hardening. Update this report after mitigations land and include verification steps (tests, configs).
