from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from amodb.apps.quality import audit_archive_size_guard as guard


def _evidence(size_bytes: int) -> dict:
    return {
        "item_type": "EVIDENCE_ARTIFACT",
        "metadata": {"size_bytes": size_bytes},
    }


def test_archive_size_guard_rejects_oversized_evidence_before_render(monkeypatch, tmp_path: Path):
    called: list[bool] = []

    def fake_render(*_args, **_kwargs):
        called.append(True)
        return 1, "a" * 64

    monkeypatch.setattr(guard, "_original_render_package", fake_render)
    with pytest.raises(HTTPException) as exc_info:
        guard.render_package_with_size_guard(
            tmp_path / "archive.zip",
            manifest_payload={},
            manifest_sha256="b" * 64,
            inventory=[_evidence(guard._MAX_EVIDENCE_INPUT_BYTES + 1)],
            timeline=[],
        )

    assert exc_info.value.status_code == 413
    assert called == []


def test_archive_size_guard_rejects_final_package_above_integer_range(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        guard,
        "_original_render_package",
        lambda *_args, **_kwargs: (guard._MAX_PERSISTED_PACKAGE_BYTES + 1, "c" * 64),
    )

    with pytest.raises(HTTPException) as exc_info:
        guard.render_package_with_size_guard(
            tmp_path / "archive.zip",
            manifest_payload={},
            manifest_sha256="d" * 64,
            inventory=[_evidence(1)],
            timeline=[],
        )

    assert exc_info.value.status_code == 413


def test_archive_size_guard_allows_supported_package(monkeypatch, tmp_path: Path):
    expected = (1234, "e" * 64)
    monkeypatch.setattr(guard, "_original_render_package", lambda *_args, **_kwargs: expected)

    result = guard.render_package_with_size_guard(
        tmp_path / "archive.zip",
        manifest_payload={},
        manifest_sha256="f" * 64,
        inventory=[_evidence(1024)],
        timeline=[],
    )

    assert result == expected
