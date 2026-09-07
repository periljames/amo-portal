"""KCAR 2025 AMO role catalogue and reporting-line rules."""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from ..accounts import access_control, models as account_models, role_registry, services as account_services
from . import governance_models, governance_schemas, models

KCAR_SOURCE_TITLE = "Civil Aviation (Approved Maintenance Organization) Regulations, 2025"
KCAR_SOURCE_REFERENCE = "Regulations 19-21"
KCAR_SOURCE_URL = "https://libraryir.parliament.go.ke/items/cb07b9ca-4f03-4622-894c-bba6f025e1df"

MANAGEMENT_LEVELS = ("STAFF", "SUPERVISOR", "MANAGER", "EXECUTIVE")

_KCAR_ROLE_CONFIG = {
    "ACCOUNTABLE_EXECUTIVE": ("AE", "EXECUTIVE", ("AE",)),
    "BASE_MAINTENANCE_MANAGER": ("BMM", "MANAGER", ("BMM", "HOBM", "HBM")),
    "LINE_MAINTENANCE_MANAGER": ("LMM", "MANAGER", ("LMM", "HOLM", "HLM")),
    "WORKSHOP_MANAGER": ("WM", "MANAGER", ("WM", "CWM", "HOW")),
    "QUALITY_MANAGER": ("QM", "MANAGER", ("QM", "HOQ")),
    "SAFETY_MANAGER": ("SM", "MANAGER", ("SM", "HOS")),
}

KCAR_ROLES = tuple(
    {
        "key": key,
        "code": config[0],
        "title": role_registry.ROLE_DEFINITIONS[key].label,
        "management_level": config[1],
        "description": role_registry.ROLE_DEFINITIONS[key].description,
        "aliases": (
            role_registry.ROLE_DEFINITIONS[key].label,
            *role_registry.ROLE_DEFINITIONS[key].aliases,
        ),
        "code_aliases": config[2],
    }
    for key, config in _KCAR_ROLE_CONFIG.items()
)

TENANT_FUNCTIONS = (
    {
        "key": "HUMAN_RESOURCES",
        "label": "Human Resources",
        "suggested_code": "HRM",
        "suggested_title": "Human Resources Manager",
    },
    {
        "key": "INFORMATION_TECHNOLOGY",
        "label": "Information Technology",
        "suggested_code": "ITM",
        "suggested_title": "Information Technology Manager",
    },
    {
        "key": "FINANCE",
        "label": "Finance",
        "suggested_code": "FM",
        "suggested_title": "Finance Manager",
    },
)

KCAR_ROLE_KEYS = frozenset(role["key"] for role in KCAR_ROLES)
TENANT_FUNCTION_KEYS = frozenset(role["key"] for role in TENANT_FUNCTIONS)

REFERENCE_POSITIONS = (
    ("QUALITY_OFFICER", "QO", "Quality Officer", "STAFF", "QUALITY_MANAGER"),
    ("DOCUMENT_CONTROL_OFFICER", "DCO", "Document Control Officer (Librarian)", "STAFF", "QUALITY_MANAGER"),
    ("QUALITY_SUPPORT_OFFICER", "QSO", "Quality Support Officer", "STAFF", "QUALITY_MANAGER"),
    ("SAFETY_OFFICER", "SO", "Safety Officer", "STAFF", "SAFETY_MANAGER"),
    ("SAFETY_CAMPAIGNER", "SC", "Safety Campaigner", "STAFF", "SAFETY_OFFICER"),
    ("LINE_MAINTENANCE_SUPERVISOR", "LMS", "Line Maintenance Supervisor", "SUPERVISOR", "LINE_MAINTENANCE_MANAGER"),
    ("LINE_QUALITY_CONTROL_OFFICER", "LQCO", "Line Quality Control Officer", "STAFF", "LINE_MAINTENANCE_MANAGER"),
    ("HANGAR_SUPERVISOR", "HS", "Hangar Supervisor", "SUPERVISOR", "BASE_MAINTENANCE_MANAGER"),
    ("HANGAR_QUALITY_CONTROL_OFFICER", "HQCO", "Hangar Quality Control Officer", "STAFF", "BASE_MAINTENANCE_MANAGER"),
    ("WORKSHOP_QUALITY_CONTROL_OFFICER", "WQCO", "Workshop Quality Control Officer", "STAFF", "WORKSHOP_MANAGER"),
    ("STORES_SUPERVISOR", "STS", "Stores Supervisor", "SUPERVISOR", "BASE_MAINTENANCE_MANAGER"),
    ("TECHNICAL_RECORDS_PLANNING_SUPERVISOR", "TRPS", "Technical Records & Planning Supervisor", "SUPERVISOR", "BASE_MAINTENANCE_MANAGER"),
    ("TECHNICAL_RECORDS_OFFICER", "TRO", "Technical Records Officer (TRO)", "STAFF", "TECHNICAL_RECORDS_PLANNING_SUPERVISOR"),
    ("CERTIFYING_ENGINEER", "LCE", "Line Certifying Engineer", "STAFF", "LINE_MAINTENANCE_SUPERVISOR"),
    ("LINE_CERTIFYING_TECHNICIAN", "LCT", "Line Certifying Technician", "STAFF", "LINE_MAINTENANCE_SUPERVISOR"),
    ("HANGAR_CERTIFYING_ENGINEER", "HCE", "Hangar Certifying Engineer", "STAFF", "HANGAR_SUPERVISOR"),
    ("CERTIFYING_TECHNICIAN", "HCT", "Hangar Certifying Technician", "STAFF", "HANGAR_SUPERVISOR"),
    ("TECHNICIAN", "HT", "Hangar Technician", "STAFF", "HANGAR_SUPERVISOR"),
    ("WORKSHOP_SPECIALIST", "WRS", "Workshop Repair Specialist (Tenant-defined)", "STAFF", "WORKSHOP_QUALITY_CONTROL_OFFICER"),
    ("SHEET_METAL_COMPOSITES_REPAIR_SPECIALIST", "SMCR", "Sheet Metal & Composites Repair Specialist", "STAFF", "WORKSHOP_QUALITY_CONTROL_OFFICER"),
    ("WHEELS_BRAKES_REPAIR_SPECIALIST", "WBR", "Wheels & Brakes Repair Specialist", "STAFF", "WORKSHOP_QUALITY_CONTROL_OFFICER"),
    ("BATTERY_SHOP_SERVICE_SPECIALIST", "BSS", "Battery Shop Service Specialist", "STAFF", "WORKSHOP_QUALITY_CONTROL_OFFICER"),
    ("GROUND_EQUIPMENT_TECHNICIAN", "GET", "Ground Equipment Operator / Technician", "STAFF", "LINE_MAINTENANCE_SUPERVISOR"),
    ("AIRCRAFT_GROOMER", "AG", "Aircraft Groomer", "STAFF", "LINE_MAINTENANCE_SUPERVISOR"),
    ("STORES_PROCUREMENT_CLERK", "SPC", "Stores & Procurement Clerk", "STAFF", "STORES_SUPERVISOR"),
)


def can_have_supervisor(position) -> bool:
    return str(getattr(position, "role_key", "") or "").upper() != "ACCOUNTABLE_EXECUTIVE"


def position_for_user_on(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    on_date: date,
):
    placement = governance_models.WorkforcePersonPlacement
    return db.query(governance_models.WorkforcePosition).join(
        placement,
        placement.position_id == governance_models.WorkforcePosition.id,
    ).filter(
        placement.amo_id == amo_id,
        placement.user_id == user_id,
        placement.placement_type == "PRIMARY",
        placement.effective_from <= on_date,
        or_(placement.effective_to.is_(None), placement.effective_to >= on_date),
        governance_models.WorkforcePosition.amo_id == amo_id,
        governance_models.WorkforcePosition.is_active.is_(True),
    ).order_by(
        placement.effective_from.desc(),
        placement.id.desc(),
    ).first()


def person_can_have_supervisor(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    on_date: date,
) -> bool:
    position = position_for_user_on(
        db,
        amo_id=amo_id,
        user_id=user_id,
        on_date=on_date,
    )
    return position is None or can_have_supervisor(position)


def require_person_can_have_supervisor(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    on_date: date,
) -> None:
    position = position_for_user_on(
        db,
        amo_id=amo_id,
        user_id=user_id,
        on_date=on_date,
    )
    if position is not None and not can_have_supervisor(position):
        raise ValueError(
            f"{position.canonical_title} is the root accountable position and cannot have a supervisor"
        )


def require_no_reporting_cycle(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    supervisor_user_id: str,
    on_date: date,
) -> None:
    """Reject direct and indirect loops in the effective contract reporting chain."""
    current = supervisor_user_id
    seen: set[str] = set()
    while current:
        if current == user_id:
            raise ValueError("This supervisor assignment would create a reporting-line cycle")
        if current in seen:
            raise ValueError("The existing reporting hierarchy contains a cycle")
        seen.add(current)
        contract = db.query(models.EmploymentContract).filter(
            models.EmploymentContract.amo_id == amo_id,
            models.EmploymentContract.user_id == current,
            models.EmploymentContract.effective_from <= on_date,
            or_(
                models.EmploymentContract.effective_to.is_(None),
                models.EmploymentContract.effective_to >= on_date,
            ),
        ).order_by(
            models.EmploymentContract.effective_from.desc(),
            models.EmploymentContract.id.desc(),
        ).first()
        current = str(contract.supervisor_user_id) if contract and contract.supervisor_user_id else ""


def _normalized(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def _role_candidates(rows, definition) -> list:
    titles = {_normalized(value) for value in definition["aliases"]}
    codes = {_normalized(value) for value in definition["code_aliases"]}
    return [
        row
        for row in rows
        if _normalized(row.canonical_title) in titles or _normalized(row.code) in codes
    ]


def _position_status(row, definition, *, match_available: bool = False):
    ready = bool(
        row is not None
        and row.is_active
        and str(row.role_source or "") == "KCAR_2025"
        and str(row.management_level or "") == definition["management_level"]
        and bool(row.is_supervisory)
    )
    return governance_schemas.HierarchyRoleStatus(
        key=definition["key"],
        code=definition["code"],
        title=definition["title"],
        management_level=definition["management_level"],
        description=definition["description"],
        status="READY" if ready else ("MATCH_AVAILABLE" if row is not None or match_available else "MISSING"),
        position_id=str(row.id) if row is not None else None,
        can_have_supervisor=definition["key"] != "ACCOUNTABLE_EXECUTIVE",
    )


def hierarchy_blueprint(db: Session, *, amo_id: str):
    rows = db.query(governance_models.WorkforcePosition).filter(
        governance_models.WorkforcePosition.amo_id == amo_id,
    ).order_by(
        governance_models.WorkforcePosition.canonical_title.asc(),
        governance_models.WorkforcePosition.id.asc(),
    ).all()
    by_key = {str(row.role_key): row for row in rows if row.role_key}
    regulatory_roles = []
    for definition in KCAR_ROLES:
        row = by_key.get(definition["key"])
        regulatory_roles.append(_position_status(
            row,
            definition,
            match_available=row is None and bool(_role_candidates(rows, definition)),
        ))
    tenant_functions = []
    definitions = {item["key"]: item for item in TENANT_FUNCTIONS}
    for key, definition in definitions.items():
        row = by_key.get(key)
        if row is None:
            row = next((candidate for candidate in rows if (
                _normalized(candidate.code) == _normalized(definition["suggested_code"])
                or _normalized(candidate.canonical_title) == _normalized(definition["suggested_title"])
            )), None)
        tenant_functions.append(governance_schemas.TenantFunctionStatus(
            key=key,
            label=definition["label"],
            suggested_code=definition["suggested_code"],
            suggested_title=definition["suggested_title"],
            status="READY" if row is not None and row.role_key == key and row.is_active else "PENDING_TENANT_SETUP",
            position_id=str(row.id) if row is not None else None,
        ))
    ready_count = sum(role.status == "READY" for role in regulatory_roles)
    return governance_schemas.HierarchyBlueprintRead(
        source_title=KCAR_SOURCE_TITLE,
        source_reference=KCAR_SOURCE_REFERENCE,
        source_url=KCAR_SOURCE_URL,
        regulatory_roles=regulatory_roles,
        tenant_functions=tenant_functions,
        required_role_count=len(regulatory_roles),
        ready_role_count=ready_count,
        missing_role_count=len(regulatory_roles) - ready_count,
    )


def _available_code(rows, *, preferred: str, current_id: str | None = None) -> str:
    used = {
        _normalized(row.code)
        for row in rows
        if current_id is None or str(row.id) != str(current_id)
    }
    if _normalized(preferred) not in used:
        return preferred
    fallback = f"KCAR-{preferred}"
    if _normalized(fallback) not in used:
        return fallback
    suffix = 2
    while _normalized(f"{fallback}-{suffix}") in used:
        suffix += 1
    return f"{fallback}-{suffix}"


def clear_current_management_supervisors(
    db: Session,
    *,
    amo_id: str,
    position_id: str,
    on_date: date,
) -> int:
    placements = db.query(governance_models.WorkforcePersonPlacement).filter(
        governance_models.WorkforcePersonPlacement.amo_id == amo_id,
        governance_models.WorkforcePersonPlacement.position_id == position_id,
        governance_models.WorkforcePersonPlacement.placement_type == "PRIMARY",
        governance_models.WorkforcePersonPlacement.effective_from <= on_date,
        or_(
            governance_models.WorkforcePersonPlacement.effective_to.is_(None),
            governance_models.WorkforcePersonPlacement.effective_to >= on_date,
        ),
    ).with_for_update().all()
    user_ids = {str(row.user_id) for row in placements}
    changed = 0
    for row in placements:
        if row.supervisor_user_id:
            row.supervisor_user_id = None
            changed += 1
    if user_ids:
        contracts = db.query(models.EmploymentContract).filter(
            models.EmploymentContract.amo_id == amo_id,
            models.EmploymentContract.user_id.in_(user_ids),
            models.EmploymentContract.effective_from <= on_date,
            or_(
                models.EmploymentContract.effective_to.is_(None),
                models.EmploymentContract.effective_to >= on_date,
            ),
            models.EmploymentContract.supervisor_user_id.is_not(None),
        ).with_for_update().all()
        for contract in contracts:
            contract.supervisor_user_id = None
            changed += 1
    return changed


def sync_account_for_position(db: Session, user, position) -> bool:
    """Synchronise a governed position's access profile to the account.

    Tenant-administrator status and personal certifying/auditor authorizations
    are independent overlays and are never created or removed here.
    """
    profile = getattr(position, "access_profile", None)
    role_key = str(getattr(profile, "base_role_key", "") or getattr(position, "role_key", "") or "")
    if role_key not in role_registry.ROLE_DEFINITIONS:
        return False
    resolved_role = role_registry.resolve_account_role(role_key)
    changed = bool(
        user.role != resolved_role
        or user.position_title != position.canonical_title
    )
    user.role = resolved_role
    user.position_title = position.canonical_title
    if profile is not None:
        access_control.assign_primary_access_profile(
            db,
            user=user,
            profile_id=str(profile.id),
            actor_user_id=None,
        )
    account_services.sync_regulated_postholder_assignment(db, user)
    return changed


def sync_current_position_accounts(
    db: Session,
    *,
    amo_id: str,
    position,
    on_date: date,
) -> int:
    placements = db.query(governance_models.WorkforcePersonPlacement).filter(
        governance_models.WorkforcePersonPlacement.amo_id == amo_id,
        governance_models.WorkforcePersonPlacement.position_id == str(position.id),
        governance_models.WorkforcePersonPlacement.placement_type == "PRIMARY",
        governance_models.WorkforcePersonPlacement.effective_from <= on_date,
        or_(
            governance_models.WorkforcePersonPlacement.effective_to.is_(None),
            governance_models.WorkforcePersonPlacement.effective_to >= on_date,
        ),
    ).all()
    user_ids = {str(row.user_id) for row in placements}
    if not user_ids:
        return 0
    users = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id.in_(user_ids),
    ).with_for_update().all()
    return sum(1 for user in users if sync_account_for_position(db, user, position))


def initialize_kcar_roles(db: Session, *, amo_id: str, on_date: date | None = None):
    access_control.ensure_tenant_access_profiles(db, amo_id=amo_id)
    profiles = {
        str(row.tenant_code): row
        for row in db.query(account_models.AuthRoleDefinition).filter(
            account_models.AuthRoleDefinition.amo_id == amo_id,
            account_models.AuthRoleDefinition.is_active.is_(True),
        ).all()
        if row.tenant_code
    }
    profiles_by_id = {str(row.id): row for row in profiles.values()}
    rows = db.query(governance_models.WorkforcePosition).options(
        selectinload(governance_models.WorkforcePosition.job_family),
        selectinload(governance_models.WorkforcePosition.grade),
    ).filter(
        governance_models.WorkforcePosition.amo_id == amo_id,
    ).with_for_update().all()
    by_key = {str(row.role_key): row for row in rows if row.role_key}
    changed = 0
    adopted = 0
    created = 0
    supervisors_cleared = 0
    accounts_synced = 0
    for definition in KCAR_ROLES:
        row = by_key.get(definition["key"])
        if row is None:
            candidates = [candidate for candidate in _role_candidates(rows, definition) if not candidate.role_key]
            row = candidates[0] if candidates else None
            if row is not None:
                adopted += 1
            else:
                row = governance_models.WorkforcePosition(
                    amo_id=amo_id,
                    code=_available_code(rows, preferred=definition["code"]),
                    canonical_title=definition["title"],
                )
                db.add(row)
                rows.append(row)
                created += 1
        canonical_code = _available_code(
            rows,
            preferred=definition["code"],
            current_id=str(row.id) if row.id else None,
        )
        desired = {
            "code": canonical_code,
            "canonical_title": definition["title"],
            "description": row.description or definition["description"],
            "role_source": "KCAR_2025",
            "role_key": definition["key"],
            "management_level": definition["management_level"],
            "is_supervisory": True,
            "is_active": True,
            "access_profile_id": str(profiles[definition["key"]].id),
        }
        if any(getattr(row, field, None) != value for field, value in desired.items()):
            changed += 1
        for field, value in desired.items():
            setattr(row, field, value)
        row.access_profile = profiles[definition["key"]]
        db.flush()
        if not can_have_supervisor(row):
            supervisors_cleared += clear_current_management_supervisors(
                db,
                amo_id=amo_id,
                position_id=str(row.id),
                on_date=on_date or date.today(),
            )
        accounts_synced += sync_current_position_accounts(
            db,
            amo_id=amo_id,
            position=row,
            on_date=on_date or date.today(),
        )
    by_key = {str(row.role_key): row for row in rows if row.role_key}
    newly_defaulted_reference_keys: set[str] = set()
    for key, code, title, level, _reports_to in REFERENCE_POSITIONS:
        row = by_key.get(key)
        if row is None:
            candidates = [candidate for candidate in rows if (
                not candidate.role_key
                and (_normalized(candidate.code) == _normalized(code) or _normalized(candidate.canonical_title) == _normalized(title))
            )]
            row = candidates[0] if candidates else governance_models.WorkforcePosition(
                amo_id=amo_id,
                code=_available_code(rows, preferred=code),
                canonical_title=title,
            )
            if not candidates:
                db.add(row)
                rows.append(row)
                created += 1
            else:
                adopted += 1
            newly_defaulted_reference_keys.add(key)
            row.role_source = "TENANT"
            row.role_key = key
            row.management_level = level
            row.is_supervisory = level in {"SUPERVISOR", "MANAGER", "EXECUTIVE"}
            row.is_active = True
            row.access_profile_id = str(profiles[key].id)
            row.access_profile = profiles[key]
        else:
            linked_profile = profiles_by_id.get(str(row.access_profile_id)) if row.access_profile_id else None
            expected_base = access_control.TEMPLATES_BY_CODE[key]["base"]
            # Preserve a tenant-custom profile only when it belongs to this
            # tenant, remains active and maps to the same stable persona.
            # Otherwise repair the unsafe or stale link to the reference
            # profile before synchronising any account.
            if linked_profile is not None and linked_profile.base_role_key == expected_base:
                row.access_profile = linked_profile
            else:
                row.access_profile_id = str(profiles[key].id)
                row.access_profile = profiles[key]
        row.description = row.description or access_control.TEMPLATES_BY_CODE[key]["description"]
        by_key[key] = row
        db.flush()

    # Apply the supplied/common AMO reporting topology after every referenced
    # position exists. Tenant titles remain editable; identifiers and parent
    # links keep the structure stable and cycle-safe.
    reporting = {
        "ACCOUNTABLE_EXECUTIVE": None,
        "QUALITY_MANAGER": "ACCOUNTABLE_EXECUTIVE",
        "SAFETY_MANAGER": "ACCOUNTABLE_EXECUTIVE",
        "BASE_MAINTENANCE_MANAGER": "ACCOUNTABLE_EXECUTIVE",
        "LINE_MAINTENANCE_MANAGER": "ACCOUNTABLE_EXECUTIVE",
        "WORKSHOP_MANAGER": "ACCOUNTABLE_EXECUTIVE",
        **{key: reports_to for key, _code, _title, _level, reports_to in REFERENCE_POSITIONS},
    }
    for key, parent_key in reporting.items():
        row = by_key.get(key)
        parent = by_key.get(parent_key) if parent_key else None
        if row is not None and (key in KCAR_ROLE_KEYS or key in newly_defaulted_reference_keys):
            row.reports_to_position_id = str(parent.id) if parent is not None else None
        if row is not None:
            accounts_synced += sync_current_position_accounts(
                db, amo_id=amo_id, position=row, on_date=on_date or date.today()
            )
    db.flush()
    result = hierarchy_blueprint(db, amo_id=amo_id)
    result.created_count = created
    result.adopted_count = adopted
    result.updated_count = changed
    result.supervisor_links_cleared = supervisors_cleared
    result.accounts_synced = accounts_synced
    return result
