# DEPLOY RUNBOOK

This runbook implements a repeatable deploy path targeting **<= 30 minutes** after last code change.

> Status note: because `portal_spec.md` is missing, some values are placeholders (`UNKNOWN__FILL_ME`).

## 1) Golden path commands

```bash
cp .env.example .env
# fill values from secret store / infra inventory
make build
make deploy
make health
```

## 2) First-time install

### Prerequisites
1. Docker Engine + Compose plugin installed on APP VM.
2. Network path from APP VM to DB VM works (`5432/tcp`).
3. EDGE VM has NGINX with `infra/nginx/nginx.conf` deployed.
4. `.env` created from `.env.example` with secrets injected from secret store.

### Steps
1. **Prepare directories**
   ```bash
   mkdir -p /opt/amo-portal/releases /opt/amo-portal/shared/{uploads,logs,backups}
   ```
2. **Pull repo and set env**
   ```bash
   git clone <repo-url> /opt/amo-portal/releases/current
   cd /opt/amo-portal/releases/current
   cp .env.example .env
   ```
3. **Validate env placeholders removed**
   ```bash
   if rg -n "PLACEHOLDER__SET_IN_SECRET_STORE|UNKNOWN__FILL_ME" .env; then echo "Fix env" && exit 1; fi
   ```
4. **Build and deploy**
   ```bash
   make build
   make deploy
   ```
5. **Deploy EDGE config**
   ```bash
   sudo cp -r infra/nginx/* /etc/nginx/
   sudo nginx -t
   sudo systemctl reload nginx
   ```
6. **Smoke check**
   ```bash
   make health
   curl -fsS http://127.0.0.1:8080/healthz
   ```

## 3) Update deploy in <= 30 minutes

1. Pull latest code:
   ```bash
   git pull --ff-only
   ```
2. Confirm DB backup before migrations:
   ```bash
   ./scripts/deploy.sh --backup-only
   ```
3. Execute idempotent deployment:
   ```bash
   ./scripts/deploy.sh
   ```
4. Validate:
   ```bash
   make health
   curl -fsS http://127.0.0.1:8080/healthz
   ```
5. Run targeted functional checks (see section 6).

## 4) Rollback in <= 10 minutes

1. Trigger rollback script:
   ```bash
   ./scripts/rollback.sh
   ```
2. Validate services:
   ```bash
   make health
   curl -fsS http://127.0.0.1:8080/healthz
   ```
3. If migration incompatibility occurred, restore DB from latest backup:
   ```bash
   # Example only; adapt to your backup tooling
   pg_restore --clean --if-exists --no-owner --dbname "$DATABASE_WRITE_URL" /opt/amo-portal/shared/backups/UNKNOWN__FILL_ME.dump
   ```

Rollback limitation:
- Schema-downgrade support is not guaranteed for every Alembic migration. If downgrade is unsafe, restore from pre-deploy DB backup.

## 5) Health checks

- Backend liveness: `GET /health`
- Backend readiness-ish: `GET /healthz` (DB + broker state)
- Frontend reachability: `GET /` via EDGE
- Stream endpoint handshake: `GET /api/events` with auth token should return SSE headers

Commands:
```bash
curl -fsS https://portal.UNKNOWN__FILL_ME/healthz
curl -i -H "Authorization: Bearer <JWT>" https://portal.UNKNOWN__FILL_ME/api/events
curl -fsS https://portal.UNKNOWN__FILL_ME/
```

## 6) Verification test plan

### Functional smoke
- Login flow works with valid credentials.
- API read/write for one tenant succeeds.
- One file upload per major module (manuals/reliability/training) succeeds.

### Upload stress
- Upload file of size `UNKNOWN__FILL_ME`.
- Concurrent uploads: `UNKNOWN__FILL_ME` clients.
- Validate 413 behavior beyond limit.

### Streaming soak (1 hour)
- Keep authenticated SSE client connected for 60 minutes.
- Validate reconnect behavior and `Last-Event-ID` replay.

### Security checks
- Confirm no secrets in repo or image env dumps.
- Run dependency scans (`npm audit`, `pip-audit`) as operational task `ASSUMPTION__REVIEW`.

## 7) Disaster recovery (DB + files + services)

1. **Restore DB**
   - Provision clean PostgreSQL instance on DB VM.
   - Restore latest verified backup.
   - Run `alembic upgrade heads` if backup predates current revision.
2. **Restore files**
   - Reattach NAS backup snapshot.
   - Restore upload directories to APP shared storage.
3. **Restore services**
   - Redeploy with `./scripts/deploy.sh`.
   - Re-run smoke and health checks.
4. **Exit criteria**
   - `/healthz` returns `status=ok` and DB true.
   - Critical workflows complete successfully.
