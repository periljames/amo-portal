"""Deterministic revision comparison and annotation migration proposals."""
from __future__ import annotations

from collections import Counter, defaultdict
import re
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.manuals import models as manual_models

from . import governance_models as gm


def _norm(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).strip()


def _structure(db: Session, revision_id: str):
    sections = db.query(manual_models.ManualSection).filter(
        manual_models.ManualSection.revision_id == revision_id,
    ).order_by(manual_models.ManualSection.order_index.asc(), manual_models.ManualSection.id.asc()).all()
    ids = [row.id for row in sections]
    blocks = db.query(manual_models.ManualBlock).filter(
        manual_models.ManualBlock.section_id.in_(ids or ["-"])
    ).order_by(manual_models.ManualBlock.section_id.asc(), manual_models.ManualBlock.order_index.asc()).all()
    grouped = defaultdict(list)
    for block in blocks:
        grouped[block.section_id].append(block)
    return sections, grouped


def compare_revisions(db: Session, source: manual_models.ManualRevision, target: manual_models.ManualRevision) -> dict[str, Any]:
    source_sections, source_blocks = _structure(db, source.id)
    target_sections, target_blocks = _structure(db, target.id)
    by_anchor = {row.anchor_slug: row for row in target_sections if row.anchor_slug}
    by_heading = defaultdict(list)
    for row in target_sections:
        by_heading[_norm(row.heading)].append(row)
    matched: set[str] = set()
    mapping: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    for section in source_sections:
        candidate = by_anchor.get(section.anchor_slug)
        strategy = "ANCHOR_EXACT" if candidate else ""
        if not candidate:
            choices = by_heading.get(_norm(section.heading), [])
            if len(choices) == 1:
                candidate = choices[0]
                strategy = "HEADING_MATCH"
        if candidate:
            matched.add(candidate.id)
            source_hashes = [row.change_hash for row in source_blocks.get(section.id, [])]
            target_hashes = [row.change_hash for row in target_blocks.get(candidate.id, [])]
            unchanged = source_hashes == target_hashes
            status = "UNCHANGED" if unchanged else "CHANGED"
            migration_status = "EXACT" if unchanged and strategy == "ANCHOR_EXACT" else "REVIEW_REQUIRED"
            confidence = 100 if migration_status == "EXACT" else 90 if strategy == "ANCHOR_EXACT" else 75
            mapping[section.id] = {
                "status": migration_status,
                "confidence_percent": confidence,
                "target_section_id": candidate.id,
                "target_anchor_slug": candidate.anchor_slug,
                "target_heading": candidate.heading,
                "strategy": strategy,
            }
        else:
            status = "REMOVED"
            mapping[section.id] = {"status": "UNRESOLVED", "confidence_percent": 0}
        items.append({
            "source_section_id": section.id,
            "source_anchor_slug": section.anchor_slug,
            "source_heading": section.heading,
            "target_section_id": candidate.id if candidate else None,
            "target_anchor_slug": candidate.anchor_slug if candidate else None,
            "target_heading": candidate.heading if candidate else None,
            "status": status,
            "strategy": strategy or "NONE",
            "source_block_count": len(source_blocks.get(section.id, [])),
            "target_block_count": len(target_blocks.get(candidate.id, [])) if candidate else 0,
        })
    for section in target_sections:
        if section.id not in matched:
            items.append({
                "source_section_id": None,
                "source_anchor_slug": None,
                "source_heading": None,
                "target_section_id": section.id,
                "target_anchor_slug": section.anchor_slug,
                "target_heading": section.heading,
                "status": "ADDED",
                "strategy": "NONE",
                "source_block_count": 0,
                "target_block_count": len(target_blocks.get(section.id, [])),
            })
    return {
        "source_revision_id": source.id,
        "target_revision_id": target.id,
        "summary": dict(Counter(item["status"] for item in items)),
        "sections": items,
        "section_map": mapping,
    }


def migration_proposal(db: Session, annotation: gm.DocumentAnnotation, comparison: dict[str, Any]) -> dict[str, Any]:
    location = db.query(gm.DocumentLocation).filter(gm.DocumentLocation.id == annotation.location_id).first()
    if not location:
        return {"strategy": "UNRESOLVED", "confidence_percent": 0, "location": {}, "reason": "Source location is missing."}
    mapped = comparison.get("section_map", {}).get(location.section_id or "")
    if mapped and mapped.get("target_section_id"):
        exact = mapped["status"] == "EXACT"
        return {
            "strategy": mapped["status"],
            "confidence_percent": int(mapped["confidence_percent"]),
            "location": {
                "location_type": location.location_type,
                "page_number": location.page_number if exact else None,
                "section_id": mapped["target_section_id"],
                "exact_quote": location.exact_quote,
                "prefix_context": location.prefix_context,
                "suffix_context": location.suffix_context,
                "normalized_rects": list(location.normalized_rects_json or []) if exact else [],
            },
            "reason": f"{mapped.get('strategy', 'SECTION')} mapped to {mapped.get('target_heading', 'target section')}",
        }
    if location.page_number:
        return {
            "strategy": "REVIEW_REQUIRED",
            "confidence_percent": 40,
            "location": {"location_type": "PAGE", "page_number": location.page_number, "normalized_rects": []},
            "reason": "Only the physical page number can be proposed; content review is required.",
        }
    return {"strategy": "UNRESOLVED", "confidence_percent": 0, "location": {}, "reason": "No stable target anchor was found."}
