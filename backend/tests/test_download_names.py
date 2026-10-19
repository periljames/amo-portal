import asyncio
from email.message import Message
from types import SimpleNamespace
from datetime import datetime, timezone

import pytest

from amodb.utils.download_names import download_name, attachment_header
from amodb.utils.download_headers import DownloadFilenameMiddleware

UUID = "f231f732-d27b-4bbd-8b47-a2816ef931d5"


@pytest.mark.parametrize("parts,extension,expected", [
    (("QAR/MO/26/006", "report", "rev-2"), "pdf", "QAR-MO-26-006-report-rev-2.pdf"),
    ((UUID + ".pdf",), ".pdf", "document.pdf"),
    ((UUID.replace("-", "") + "_Audit report.pdf",), "pdf", "Audit report.pdf"),
    ((f"training-{UUID}-report.xlsx",), "xlsx", "training-report.xlsx"),
    (("CON",), "pdf", "file-CON.pdf"),
    (("Résumé Rev 01",), "docx", "Résumé Rev 01.docx"),
])
def test_public_download_names(parts, extension, expected):
    assert download_name(*parts, extension=extension) == expected


def test_long_names_keep_extension_and_no_header_injection():
    filename = download_name("é" * 300, extension="xlsx")
    assert len(filename) == 180
    assert filename.endswith(".xlsx")
    header = attachment_header(download_name("Résumé\r\nX-Evil: yes", extension="pdf"))
    header.encode("latin1")
    assert "\r" not in header and "\n" not in header
    parsed = Message()
    parsed["Content-Disposition"] = header
    # email.message prefers the ASCII fallback, browsers prefer filename*.
    assert "filename*=UTF-8''R%C3%A9sum%C3%A9" in header


@pytest.mark.parametrize("kind", ["attachment", "inline"])
def test_legacy_header_guard_keeps_body_hash_and_other_headers(kind):
    messages = []
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [
            (b"content-disposition", f'{kind}; filename="CAR-SAF-26-005-{UUID}.zip"'.encode()),
            (b"etag", b'"unchanged"'), (b"content-length", b"3"),
        ]})
        await send({"type": "http.response.body", "body": b"zip", "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
    async def receive():
        return {"type": "http.request"}
    async def send(message):
        messages.append(message)
    asyncio.run(DownloadFilenameMiddleware(app)({"type": "http"}, receive, send))
    headers = dict(messages[0]["headers"])
    assert UUID.encode() not in headers[b"content-disposition"]
    assert f'{kind}; filename="CAR-SAF-26-005.zip"'.encode() in headers[b"content-disposition"]
    assert headers[b"etag"] == b'"unchanged"'
    assert headers[b"content-length"] == b"3"
    assert messages[1]["body"] == b"zip" and messages[1]["more_body"]


def test_training_job_download_uses_code_and_completion_time(tmp_path, monkeypatch):
    from amodb.apps.training import operating_router
    from amodb.jobs import training_report_jobs
    path = tmp_path / f"{UUID}.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    row = SimpleNamespace(status="COMPLETED", report_code="COMPLIANCE_SUMMARY", completed_at=datetime(2026, 10, 18, 12, 30, 45, tzinfo=timezone.utc), created_at=None)
    class Query:
        def filter(self, *args): return self
        def first(self): return row
    db = SimpleNamespace(query=lambda *args: Query())
    monkeypatch.setattr(operating_router, "tenant_id_for", lambda user: "tenant")
    monkeypatch.setattr(training_report_jobs, "resolved_artifact_path", lambda job: path)
    response = operating_router.download_report_job(UUID, db=db, current_user=SimpleNamespace())
    assert response.filename == "training-compliance-summary-2026-10-18-123045.pdf"
    assert response.path == path


def test_evidence_pack_keeps_duplicate_attachments_distinct():
    import io
    import zipfile
    from amodb.apps.exports.evidence_pack import _write_zip
    output = _write_zip([("attachments/evidence.pdf", b"first"), ("attachments/Evidence.pdf", b"second")])
    with zipfile.ZipFile(io.BytesIO(output)) as archive:
        assert archive.namelist() == ["attachments/evidence.pdf", "attachments/Evidence (2).pdf"]
        assert archive.read("attachments/evidence.pdf") == b"first"
        assert archive.read("attachments/Evidence (2).pdf") == b"second"
