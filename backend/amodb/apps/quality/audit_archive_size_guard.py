from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from . import audit_archive_package_router as package


# QualityAuditArchiveManifest.package_size_bytes is currently backed by a
# PostgreSQL INTEGER. Bound archive creation before persistence so ZIP64 output
# can never overflow that governed column. The 2 GB evidence-input cap leaves
# headroom for the manifest, indexes, timeline and ZIP metadata; the final size
# check remains authoritative for every package.
_MAX_PERSISTED_PACKAGE_BYTES = 2_147_483_647
_MAX_EVIDENCE_INPUT_BYTES = 2_000_000_000
_original_render_package = package._render_package


def _evidence_input_size(inventory: list[dict[str, Any]]) -> int:
    total = 0
    for item in inventory:
        if item.get("item_type") != "EVIDENCE_ARTIFACT":
            continue
        metadata = item.get("metadata") or {}
        raw_size = metadata.get("size_bytes")
        if raw_size is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Governed audit evidence is missing its recorded size.",
            )
        try:
            size = int(raw_size)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Governed audit evidence has an invalid recorded size.",
            ) from exc
        if size < 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Governed audit evidence has an invalid negative size.",
            )
        total += size
        if total > _MAX_EVIDENCE_INPUT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    "Audit evidence exceeds the supported aggregate archive size. "
                    "Split the retained evidence set before generating the governed package."
                ),
            )
    return total


def render_package_with_size_guard(
    path,
    *,
    manifest_payload: dict[str, Any],
    manifest_sha256: str,
    inventory: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
) -> tuple[int, str]:
    """Keep ZIP64 package creation inside the persisted INTEGER size contract."""

    _evidence_input_size(inventory)
    package_size, package_sha256 = _original_render_package(
        path,
        manifest_payload=manifest_payload,
        manifest_sha256=manifest_sha256,
        inventory=inventory,
        timeline=timeline,
    )
    if package_size > _MAX_PERSISTED_PACKAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                "Generated audit archive exceeds the supported package size. "
                "Split the retained evidence set before generating the governed package."
            ),
        )
    return package_size, package_sha256


# Archive endpoint functions resolve this module global when invoked, so the
# bound applies to the canonical package lifecycle without duplicating it.
package._render_package = render_package_with_size_guard
