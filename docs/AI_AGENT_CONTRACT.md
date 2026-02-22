# AI AGENT CONTRACT (MANDATORY)

Every future AI coding agent modifying this repository MUST follow these rules.

## 1) Verify before changing
- Inspect existing files/services/config first.
- Do not duplicate existing functionality.
- If requirement is unclear, mark as `UNKNOWN__FILL_ME` instead of guessing.

## 2) Preserve conventions
- Keep established language/framework patterns (FastAPI backend, Vite React frontend, Alembic migrations).
- Do not introduce conflicting deployment stacks without explicit repo evidence.
- Prefer minimal, reversible changes.

## 3) Testing and command transparency
- Run relevant tests/checks for modified scope.
- Report exact commands executed and outcomes.
- If checks cannot run, document why with actionable fallback.

## 4) Migration and rollback safety
- Any schema change must include:
  - migration script,
  - backward-risk note,
  - rollback/restore instructions.
- Before production migration, trigger backup precheck.

## 5) Security obligations
- Never commit secrets or credentials.
- Respect least privilege for DB users and service accounts.
- Document security implications for auth, uploads, and tenant boundaries.

## 6) Documentation obligations
- Update production docs/runbooks when behavior or infrastructure changes.
- Update env var documentation (`.env.example`) for any new config.
- Keep `UNKNOWN__FILL_ME` entries discoverable until finalized.

## 7) Release quality gate
A change is not complete unless all are true:
1. Code and docs aligned.
2. Deployment/update/rollback steps validated.
3. Security + performance impact acknowledged.
4. No duplicate or conflicting infra artifacts introduced.
