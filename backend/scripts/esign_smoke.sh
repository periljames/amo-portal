#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -n "${DATABASE_URL:-}" || -n "${DATABASE_WRITE_URL:-}" ]]; then
  echo "[esign_smoke] upgrading schema to heads"
  alembic -c amodb/alembic.ini upgrade heads
else
  echo "[esign_smoke] DATABASE_URL not set; running deterministic test-db smoke path"
fi

echo "[esign_smoke] running esign test suite"
pytest amodb/apps/esign/tests -q

echo "[esign_smoke] running deterministic verification-token smoke"
export DATABASE_URL="${DATABASE_URL:-sqlite:///tmp_esign_smoke.db}"
export DATABASE_WRITE_URL="${DATABASE_WRITE_URL:-$DATABASE_URL}"
python - <<'PY'
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from reportlab.pdfgen import canvas

from amodb.apps.esign import models, services, utils

engine = create_engine("sqlite:///:memory:")
for table in [
    models.ESignDocumentVersion.__table__,
    models.ESignSignatureRequest.__table__,
    models.ESignSignedArtifact.__table__,
    models.ESignVerificationToken.__table__,
    models.ESignSigner.__table__,
]:
    table.create(bind=engine, checkfirst=True)

Session = sessionmaker(bind=engine, expire_on_commit=False)
db = Session()
p = Path("/tmp/esign_smoke.pdf")
c = canvas.Canvas(str(p)); c.drawString(50, 750, "smoke"); c.save()

dv = models.ESignDocumentVersion(tenant_id="amo-smoke", document_id="DOC", version_no=1, storage_ref=str(p), content_sha256=utils.sha256_hex_bytes(p.read_bytes()))
db.add(dv); db.flush()
req = models.ESignSignatureRequest(tenant_id="amo-smoke", doc_version_id=dv.id, title="Smoke", created_by_user_id="u")
db.add(req); db.flush()
art = models.ESignSignedArtifact(tenant_id="amo-smoke", signature_request_id=req.id, doc_version_id=dv.id, storage_ref=str(p), signed_content_sha256=utils.sha256_hex_bytes(p.read_bytes()))
db.add(art); db.flush()
tok = models.ESignVerificationToken(tenant_id="amo-smoke", artifact_id=art.id, token="smoketoken")
db.add(tok); db.commit()

services._audit = lambda *args, **kwargs: None
res = services.verify_public_token(db, "smoketoken")
assert res.valid is True and res.storage_integrity_valid is True
print("[esign_smoke] token verification flow ok")
PY

echo "[esign_smoke] completed"
