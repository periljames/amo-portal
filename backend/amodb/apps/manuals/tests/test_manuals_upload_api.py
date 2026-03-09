from __future__ import annotations

from io import BytesIO
import zipfile

import asyncio
import pytest
from fastapi import HTTPException, UploadFile

from amodb.apps.accounts.models import AMO, AccountRole, User
from amodb.apps.manuals import models
from amodb.apps.manuals.router import preview_docx_upload, upload_docx_revision


class _Request:
    class _Client:
        host = "127.0.0.1"

    client = _Client()
    headers = {"user-agent": "pytest"}


def _docx_bytes(*paragraphs: str) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f"<w:document><w:body>{body}</w:body></w:document>"
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


def _seed(db_session):
    amo = AMO(amo_code="AMO1", name="Demo", login_slug="demo")
    user = User(
        amo=amo,
        staff_code="S001",
        email="qa@example.com",
        first_name="Q",
        last_name="A",
        full_name="QA",
        role=AccountRole.QUALITY_MANAGER,
        hashed_password="x",
    )
    db_session.add_all([amo, user])
    db_session.flush()
    db_session.add(models.Tenant(amo_id=amo.id, slug="demo", name="Demo", settings_json={"ack_due_days": 10}))
    db_session.commit()
    return user


def test_preview_docx_upload_returns_parsed_content(db_session):
    user = _seed(db_session)
    file = UploadFile(filename="manual.docx", file=BytesIO(_docx_bytes("INTRO", "Line 2")))

    out = asyncio.run(preview_docx_upload("demo", file=file, db=db_session, current_user=user))

    assert out["filename"] == "manual.docx"
    assert out["paragraph_count"] >= 1
    assert out["sample"]


def test_upload_docx_revision_creates_revision(db_session):
    user = _seed(db_session)
    file = UploadFile(filename="manual.docx", file=BytesIO(_docx_bytes("MM", "Body")))

    out = asyncio.run(upload_docx_revision(
        "demo",
        request=_Request(),
        code="MOM-1",
        title="Maintenance Manual",
        rev_number="1",
        issue_number="1",
        manual_type="GENERAL",
        owner_role="Library",
        change_log="Updated ATA references",
        file=file,
        db=db_session,
        current_user=user,
    ))

    assert out["manual_id"]
    assert out["revision_id"]
    rev = db_session.query(models.ManualRevision).filter(models.ManualRevision.id == out["revision_id"]).first()
    assert rev is not None and "Updated ATA references" in (rev.notes or "")


def test_preview_docx_upload_rejects_invalid_file(db_session):
    user = _seed(db_session)
    file = UploadFile(filename="manual.docx", file=BytesIO(b"not-a-zip"))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(preview_docx_upload("demo", file=file, db=db_session, current_user=user))

    assert exc.value.status_code == 400
    assert "Invalid DOCX" in str(exc.value.detail)
