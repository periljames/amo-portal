from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import governance, models, schemas


class ContentSourceCurrentness(BaseModel):
    source_id: str
    source_reference: str
    source_revision: str
    publication_id: str | None
    publication_revision_id: str | None
    temporary_revision_id: str | None
    status: str
    detail: str


class ContentPackCurrentnessRead(BaseModel):
    pack: schemas.ContentPackRead
    published_revision: schemas.ContentRevisionRead | None
    status: str
    source_states: list[ContentSourceCurrentness] = Field(default_factory=list)


class PublicationContentImpactItem(BaseModel):
    pack_id: str
    pack_code: str
    pack_series: str | None
    content_revision_id: str
    content_revision_code: str
    content_revision_status: str
    source_id: str
    source_revision: str
    publication_revision_id: str
    temporary_revision_id: str | None
    relationship_status: str


def _current_publication_revision(
    publication: models.AircraftOemPublication,
) -> models.AircraftOemPublicationRevision | None:
    rows = [row for row in publication.revisions if row.status == "CURRENT"]
    if len(rows) > 1:
        raise HTTPException(
            status_code=409,
            detail="OEM publication contains multiple CURRENT revisions and requires data repair",
        )
    return rows[0] if rows else None


def _source_state(
    db: Session,
    source: models.AircraftContentPackSource,
) -> ContentSourceCurrentness:
    if not source.publication_revision_id:
        return ContentSourceCurrentness(
            source_id=source.id,
            source_reference=source.reference,
            source_revision=source.source_revision,
            publication_id=None,
            publication_revision_id=None,
            temporary_revision_id=source.temporary_revision_id,
            status="UNREGISTERED_SOURCE",
            detail="Source is not linked to a governed OEM publication revision",
        )
    bound = db.get(
        models.AircraftOemPublicationRevision,
        source.publication_revision_id,
    )
    if not bound:
        return ContentSourceCurrentness(
            source_id=source.id,
            source_reference=source.reference,
            source_revision=source.source_revision,
            publication_id=None,
            publication_revision_id=source.publication_revision_id,
            temporary_revision_id=source.temporary_revision_id,
            status="BROKEN_LINEAGE",
            detail="Linked OEM publication revision no longer resolves",
        )
    publication = bound.publication
    current = _current_publication_revision(publication)
    if current is None:
        return ContentSourceCurrentness(
            source_id=source.id,
            source_reference=source.reference,
            source_revision=source.source_revision,
            publication_id=publication.id,
            publication_revision_id=bound.id,
            temporary_revision_id=source.temporary_revision_id,
            status="NO_CURRENT_PUBLICATION",
            detail="OEM publication has no CURRENT revision",
        )
    if bound.id != current.id:
        return ContentSourceCurrentness(
            source_id=source.id,
            source_reference=source.reference,
            source_revision=source.source_revision,
            publication_id=publication.id,
            publication_revision_id=bound.id,
            temporary_revision_id=source.temporary_revision_id,
            status="SUPERSEDED_SOURCE",
            detail=(
                f"Baseline uses OEM revision {bound.revision_code}; current OEM revision is {current.revision_code}"
            ),
        )
    if source.temporary_revision_id:
        temporary = db.get(
            models.AircraftOemTemporaryRevision,
            source.temporary_revision_id,
        )
        if not temporary or temporary.publication_revision_id != bound.id:
            return ContentSourceCurrentness(
                source_id=source.id,
                source_reference=source.reference,
                source_revision=source.source_revision,
                publication_id=publication.id,
                publication_revision_id=bound.id,
                temporary_revision_id=source.temporary_revision_id,
                status="BROKEN_LINEAGE",
                detail="Linked Temporary Revision does not resolve against the bound OEM revision",
            )
        if temporary.status != "ACTIVE":
            return ContentSourceCurrentness(
                source_id=source.id,
                source_reference=source.reference,
                source_revision=source.source_revision,
                publication_id=publication.id,
                publication_revision_id=bound.id,
                temporary_revision_id=temporary.id,
                status="CLOSED_TEMPORARY_REVISION",
                detail=(
                    f"Baseline uses Temporary Revision {temporary.temporary_revision_code}, now {temporary.status}"
                ),
            )
    governed = governance.governed_publication_currentness(
        db,
        publication=publication,
    )
    if governed.currentness_status in {
        "CANDIDATE_REVIEW_REQUIRED",
        "TEMPORARY_REVISION_REVIEW_REQUIRED",
        "SOURCE_CHANGE_DETECTED",
        "SOURCE_CHECK_REQUIRED",
    }:
        return ContentSourceCurrentness(
            source_id=source.id,
            source_reference=source.reference,
            source_revision=source.source_revision,
            publication_id=publication.id,
            publication_revision_id=bound.id,
            temporary_revision_id=source.temporary_revision_id,
            status="SOURCE_REVIEW_REQUIRED",
            detail=f"OEM publication currentness is {governed.currentness_status}",
        )
    return ContentSourceCurrentness(
        source_id=source.id,
        source_reference=source.reference,
        source_revision=source.source_revision,
        publication_id=publication.id,
        publication_revision_id=bound.id,
        temporary_revision_id=source.temporary_revision_id,
        status="CURRENT",
        detail="Source lineage matches the current governed OEM publication state",
    )


def content_pack_currentness(
    db: Session,
    *,
    pack: models.AircraftContentPack,
) -> ContentPackCurrentnessRead:
    published = [row for row in pack.revisions if row.status == "PUBLISHED"]
    if len(published) > 1:
        raise HTTPException(
            status_code=409,
            detail="Content pack contains multiple PUBLISHED revisions and requires data repair",
        )
    if not published:
        return ContentPackCurrentnessRead(
            pack=schemas.ContentPackRead.model_validate(pack),
            published_revision=None,
            status="NO_PUBLISHED_BASELINE",
            source_states=[],
        )
    revision = published[0]
    states = [_source_state(db, source) for source in revision.sources]
    if not states:
        status = "NO_CONTROLLED_SOURCE"
    elif (pack.series or "").strip() and any(
        state.status == "UNREGISTERED_SOURCE" for state in states
    ):
        status = "UNGOVERNED_SOURCE"
    elif any(
        state.status in {
            "BROKEN_LINEAGE",
            "NO_CURRENT_PUBLICATION",
            "SUPERSEDED_SOURCE",
            "CLOSED_TEMPORARY_REVISION",
        }
        for state in states
    ):
        status = "SOURCE_SUPERSEDED"
    elif any(state.status == "SOURCE_REVIEW_REQUIRED" for state in states):
        status = "SOURCE_REVIEW_REQUIRED"
    else:
        status = "CURRENT"
    return ContentPackCurrentnessRead(
        pack=schemas.ContentPackRead.model_validate(pack),
        published_revision=schemas.ContentRevisionRead.model_validate(revision),
        status=status,
        source_states=states,
    )


def publication_content_impact(
    db: Session,
    *,
    publication: models.AircraftOemPublication,
) -> list[PublicationContentImpactItem]:
    revision_ids = [row.id for row in publication.revisions]
    if not revision_ids:
        return []
    current = _current_publication_revision(publication)
    sources = (
        db.query(models.AircraftContentPackSource)
        .filter(
            models.AircraftContentPackSource.publication_revision_id.in_(revision_ids)
        )
        .all()
    )
    result: list[PublicationContentImpactItem] = []
    for source in sources:
        revision = source.revision
        pack = revision.pack
        if current is None:
            relationship = "NO_CURRENT_PUBLICATION"
        elif source.publication_revision_id != current.id:
            relationship = "USES_SUPERSEDED_PUBLICATION_REVISION"
        elif source.temporary_revision_id:
            temporary = db.get(
                models.AircraftOemTemporaryRevision,
                source.temporary_revision_id,
            )
            relationship = (
                "CURRENT"
                if temporary and temporary.status == "ACTIVE"
                else "USES_CLOSED_TEMPORARY_REVISION"
            )
        else:
            relationship = "CURRENT"
        result.append(
            PublicationContentImpactItem(
                pack_id=pack.id,
                pack_code=pack.code,
                pack_series=pack.series,
                content_revision_id=revision.id,
                content_revision_code=revision.revision_code,
                content_revision_status=revision.status,
                source_id=source.id,
                source_revision=source.source_revision,
                publication_revision_id=source.publication_revision_id,
                temporary_revision_id=source.temporary_revision_id,
                relationship_status=relationship,
            )
        )
    return sorted(
        result,
        key=lambda row: (
            row.pack_code,
            row.content_revision_code,
            row.source_revision,
        ),
    )
