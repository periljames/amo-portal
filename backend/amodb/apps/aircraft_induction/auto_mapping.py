from __future__ import annotations

from . import models
from . import services as base


_original_stage = base.stage_parsed_datasets


def _ensure_mapping(db, *, induction, parsed_item, actor):
    profile = base.find_mapping_profile(
        db,
        amo_id=induction.amo_id,
        dataset=parsed_item.dataset,
        fingerprint=parsed_item.fingerprint,
    )
    if profile:
        return profile

    # Normalized headers are already canonical candidates. Create a tenant
    # mapping version immediately so a new source schema can be validated and
    # reconciled in one session, then refined and reused for later tails.
    identity_mapping = {header: header for header in parsed_item.headers if header}
    profile = models.ImportMappingProfile(
        amo_id=induction.amo_id,
        scope="TENANT",
        name=f"Auto {induction.source_system or 'GENERIC'} {parsed_item.dataset} {parsed_item.fingerprint[:8]}",
        version=1,
        source_system=(induction.source_system or "GENERIC").strip().upper(),
        source_version=None,
        dataset=parsed_item.dataset,
        fingerprint=parsed_item.fingerprint,
        header_signature_json=parsed_item.headers,
        mapping_json=identity_mapping,
        transformations_json={},
        defaults_json={},
        validation_json={
            "generated_from_induction_id": induction.id,
            "review_status": "DRAFT_AUTO_MAPPING",
        },
        status="ACTIVE",
        created_by_user_id=actor.id,
    )
    db.add(profile)
    db.flush()
    return profile


def stage_parsed_datasets(db, induction, parsed, actor):
    parsed = list(parsed)
    for item in parsed:
        _ensure_mapping(db, induction=induction, parsed_item=item, actor=actor)
    return _original_stage(db, induction, parsed, actor)


base.stage_parsed_datasets = stage_parsed_datasets
