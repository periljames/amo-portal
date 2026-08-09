from __future__ import annotations

from typing import Any

from . import backend_currentness, governance, models


_INSTALLED = False
_ORIGINAL: Any = None


def content_pack_currentness(db, *, pack):
    result = _ORIGINAL(db, pack=pack)
    revision = result.published_revision
    if revision is None or result.status not in {"CURRENT", "SOURCE_REVIEW_REQUIRED"}:
        return result

    persisted = db.get(models.AircraftContentPackRevision, revision.id)
    if not persisted:
        return result

    by_publication: dict[str, list[models.AircraftContentPackSource]] = {}
    for source in persisted.sources:
        if not source.publication_revision_id:
            continue
        publication_revision = db.get(
            models.AircraftOemPublicationRevision,
            source.publication_revision_id,
        )
        if not publication_revision:
            continue
        by_publication.setdefault(publication_revision.publication_id, []).append(source)

    source_states = list(result.source_states)
    missing_any = False
    for publication_id, sources in by_publication.items():
        publication = db.get(models.AircraftOemPublication, publication_id)
        if not publication:
            continue
        governed = governance.governed_publication_currentness(
            db,
            publication=publication,
        )
        active = {row.id: row for row in governed.active_temporary_revisions}
        represented = {
            source.temporary_revision_id
            for source in sources
            if source.temporary_revision_id
        }
        for temporary_revision_id in sorted(set(active) - represented):
            temporary = active[temporary_revision_id]
            missing_any = True
            source_states.append(
                backend_currentness.ContentSourceCurrentness(
                    source_id=f"MISSING_TR:{temporary.id}",
                    source_reference=publication.publication_code,
                    source_revision=temporary.temporary_revision_code,
                    publication_id=publication.id,
                    publication_revision_id=governed.current_revision.id
                    if governed.current_revision
                    else None,
                    temporary_revision_id=temporary.id,
                    status="MISSING_ACTIVE_TEMPORARY_REVISION",
                    detail=(
                        f"Active Temporary Revision {temporary.temporary_revision_code} is not represented "
                        "in the published OEM baseline"
                    ),
                )
            )
    if missing_any:
        return result.model_copy(
            update={
                "status": "SOURCE_REVIEW_REQUIRED",
                "source_states": source_states,
            }
        )
    return result


def install() -> None:
    global _INSTALLED, _ORIGINAL
    if _INSTALLED:
        return
    _ORIGINAL = backend_currentness.content_pack_currentness
    backend_currentness.content_pack_currentness = content_pack_currentness
    _INSTALLED = True
