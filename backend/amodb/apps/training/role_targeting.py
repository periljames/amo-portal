"""Stable access-profile targeting for training applicability rules.

Tenant-facing role names are deliberately editable. Training obligations must
therefore bind to ``AuthRoleDefinition.id`` and use text only as a historical
display snapshot or as compatibility for requirements created before the
tenant access-profile framework existed.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy.orm import Session

from ..accounts import access_control
from ..accounts import models as account_models


def normalize_role_term(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(value or "").strip().upper()).strip()


def profile_terms(profile: account_models.AuthRoleDefinition | None) -> set[str]:
    if profile is None:
        return set()
    return {
        normalized
        for normalized in (
            normalize_role_term(profile.tenant_code),
            normalize_role_term(profile.display_name),
            normalize_role_term(profile.base_role_key),
        )
        if normalized
    }


def user_role_terms(
    user: account_models.User,
    profile: account_models.AuthRoleDefinition | None,
) -> set[str]:
    values = profile_terms(profile)
    position = normalize_role_term(getattr(user, "position_title", None))
    if position:
        values.add(position)
    return values


def primary_profiles_for_users(
    db: Session,
    *,
    amo_id: str,
    user_ids: Iterable[str],
) -> dict[str, account_models.AuthRoleDefinition]:
    return access_control.primary_access_profiles_for_users(
        db,
        amo_id=amo_id,
        user_ids=user_ids,
    )


def requirement_matches_user(
    requirement: object,
    *,
    user: account_models.User,
    profile: account_models.AuthRoleDefinition | None,
) -> bool:
    stable_profile_id = str(getattr(requirement, "access_profile_id", None) or "")
    if stable_profile_id:
        return profile is not None and str(profile.id) == stable_profile_id
    legacy_role = normalize_role_term(getattr(requirement, "job_role", None))
    return bool(legacy_role and legacy_role in user_role_terms(user, profile))


def resolve_active_profile(
    db: Session,
    *,
    amo_id: str,
    profile_id: str,
) -> account_models.AuthRoleDefinition | None:
    return db.query(account_models.AuthRoleDefinition).filter(
        account_models.AuthRoleDefinition.id == profile_id,
        account_models.AuthRoleDefinition.amo_id == amo_id,
        account_models.AuthRoleDefinition.is_active.is_(True),
    ).first()


def resolve_legacy_profile(
    db: Session,
    *,
    amo_id: str,
    role_text: str | None,
) -> account_models.AuthRoleDefinition | None:
    """Map an exact legacy/import label to one unambiguous active profile."""
    term = normalize_role_term(role_text)
    if not term:
        return None
    rows = db.query(account_models.AuthRoleDefinition).filter(
        account_models.AuthRoleDefinition.amo_id == amo_id,
        account_models.AuthRoleDefinition.is_active.is_(True),
    ).all()
    matches = [row for row in rows if term in profile_terms(row)]
    return matches[0] if len(matches) == 1 else None


def profile_display_name(profile: account_models.AuthRoleDefinition) -> str:
    return str(profile.display_name or profile.tenant_code or profile.base_role_key or profile.id)
