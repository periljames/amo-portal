"""Canonical portal account roles and legacy AMO role aliases.

The account role is an access persona, while WorkforcePosition remains the
employment/organisation record.  KCAR 2018 labels and tenant abbreviations are
accepted at API boundaries, but only the KCAR 2025 canonical key is persisted.
"""
from __future__ import annotations

from dataclasses import dataclass
import enum
import re
from typing import Iterable


def normalize_role_token(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").strip().upper()).strip("_")


class AccountRole(str, enum.Enum):
    SUPERUSER = "SUPERUSER"
    AMO_ADMIN = "AMO_ADMIN"
    USER = "USER"
    ACCOUNTABLE_EXECUTIVE = "ACCOUNTABLE_EXECUTIVE"
    BASE_MAINTENANCE_MANAGER = "BASE_MAINTENANCE_MANAGER"
    LINE_MAINTENANCE_MANAGER = "LINE_MAINTENANCE_MANAGER"
    WORKSHOP_MANAGER = "WORKSHOP_MANAGER"
    QUALITY_MANAGER = "QUALITY_MANAGER"
    SAFETY_MANAGER = "SAFETY_MANAGER"
    PLANNING_ENGINEER = "PLANNING_ENGINEER"
    PRODUCTION_ENGINEER = "PRODUCTION_ENGINEER"
    CERTIFYING_ENGINEER = "CERTIFYING_ENGINEER"
    CERTIFYING_TECHNICIAN = "CERTIFYING_TECHNICIAN"
    TECHNICIAN = "TECHNICIAN"
    STORES = "STORES"
    VIEW_ONLY = "VIEW_ONLY"
    FINANCE_MANAGER = "FINANCE_MANAGER"
    ACCOUNTS_OFFICER = "ACCOUNTS_OFFICER"
    STORES_MANAGER = "STORES_MANAGER"
    STOREKEEPER = "STOREKEEPER"
    PROCUREMENT_OFFICER = "PROCUREMENT_OFFICER"
    QUALITY_INSPECTOR = "QUALITY_INSPECTOR"
    QUALITY_OFFICER = "QUALITY_OFFICER"
    AUDITOR = "AUDITOR"

    @classmethod
    def _missing_(cls, value: object):
        canonical = canonical_role_key(value)
        return cls.__members__.get(canonical) if canonical else None


@dataclass(frozen=True)
class AccountRoleDefinition:
    key: str
    label: str
    category: str
    description: str
    aliases: tuple[str, ...] = ()
    regulated: bool = False
    workforce_role_key: str | None = None
    can_manage_accounts: bool = False
    can_have_supervisor: bool = True
    permission_summary: tuple[str, ...] = ()


_DEFINITIONS = (
    AccountRoleDefinition(
        key="SUPERUSER",
        label="Platform superuser",
        category="PLATFORM",
        description="Global platform support and control; not an AMO management appointment.",
        aliases=("root", "platform admin", "platform administrator"),
        can_manage_accounts=True,
        can_have_supervisor=False,
        permission_summary=("Platform administration",),
    ),
    AccountRoleDefinition(
        key="AMO_ADMIN",
        label="AMO administrator",
        category="ADMINISTRATION",
        description="Tenant account, configuration and access administration; not a regulatory management appointment.",
        aliases=("amo admin", "amo administrator", "tenant admin", "tenant administrator"),
        can_manage_accounts=True,
        permission_summary=("User administration", "Tenant configuration"),
    ),
    AccountRoleDefinition(
        key="USER",
        label="User",
        category="GENERAL",
        description="Standard employee self-service access. Operational privileges require an explicit role or grant.",
        aliases=("employee", "staff", "portal user"),
        permission_summary=("Own roster", "Own leave", "Own attendance"),
    ),
    AccountRoleDefinition(
        key="ACCOUNTABLE_EXECUTIVE",
        label="Accountable Executive",
        category="KCAR_2025_MANAGEMENT",
        description="Final AMO accountability and authority for resources, safety and effective performance.",
        aliases=(
            "accountable", "accountable executive", "accountable manager", "accountable_manager",
            "accountable person", "ae", "ceo", "chief executive officer",
        ),
        regulated=True,
        workforce_role_key="ACCOUNTABLE_EXECUTIVE",
        can_have_supervisor=False,
        permission_summary=("Management oversight", "Accountable approvals", "Roster publication oversight"),
    ),
    AccountRoleDefinition(
        key="BASE_MAINTENANCE_MANAGER",
        label="Base Maintenance Manager",
        category="KCAR_2025_MANAGEMENT",
        description="Controls approved base-maintenance activity and resulting corrective action.",
        aliases=(
            "base maintenance manager", "head of base maintenance", "head base maintenance",
            "base maintenance head", "head of base maitenance", "head of base maintainance",
            "bmm", "hobm", "hbm",
        ),
        regulated=True,
        workforce_role_key="BASE_MAINTENANCE_MANAGER",
        can_have_supervisor=False,
        permission_summary=("Base maintenance control", "Department roster approval", "Leave review"),
    ),
    AccountRoleDefinition(
        key="LINE_MAINTENANCE_MANAGER",
        label="Line Maintenance Manager",
        category="KCAR_2025_MANAGEMENT",
        description="Controls line maintenance, defect rectification and resulting corrective action.",
        aliases=(
            "line maintenance manager", "head of line maintenance", "head line maintenance",
            "line maintenance head", "head of line maitenance", "head of line maintainance",
            "lmm", "holm", "hlm",
        ),
        regulated=True,
        workforce_role_key="LINE_MAINTENANCE_MANAGER",
        can_have_supervisor=False,
        permission_summary=("Line maintenance control", "Department roster approval", "Leave review"),
    ),
    AccountRoleDefinition(
        key="WORKSHOP_MANAGER",
        label="Workshop Manager",
        category="KCAR_2025_MANAGEMENT",
        description="Controls approved component-workshop activity and resulting corrective action.",
        aliases=(
            "workshop manager", "head of workshop", "workshop head", "component workshop manager",
            "head of component maintenance", "wm", "how",
        ),
        regulated=True,
        workforce_role_key="WORKSHOP_MANAGER",
        can_have_supervisor=False,
        permission_summary=("Workshop control", "Department roster approval", "Leave review"),
    ),
    AccountRoleDefinition(
        key="QUALITY_MANAGER",
        label="Quality Manager",
        category="KCAR_2025_MANAGEMENT",
        description="Monitors AMO compliance independently and coordinates regulatory compliance activities.",
        aliases=(
            "quality manager", "head of quality", "quality head", "compliance monitoring manager",
            "qm", "hoq",
        ),
        regulated=True,
        workforce_role_key="QUALITY_MANAGER",
        can_have_supervisor=False,
        permission_summary=("Quality management", "Compliance monitoring", "Controlled-document quality review"),
    ),
    AccountRoleDefinition(
        key="SAFETY_MANAGER",
        label="Safety Manager",
        category="KCAR_2025_MANAGEMENT",
        description="Implements and maintains the AMO safety management system.",
        aliases=("safety manager", "head of safety", "safety head", "sm", "hos"),
        regulated=True,
        workforce_role_key="SAFETY_MANAGER",
        can_have_supervisor=False,
        permission_summary=("Safety management", "Safety reporting", "Safety assurance"),
    ),
    AccountRoleDefinition("PLANNING_ENGINEER", "Planning Engineer", "OPERATIONAL", "Maintenance planning access."),
    AccountRoleDefinition("PRODUCTION_ENGINEER", "Production Engineer", "OPERATIONAL", "Production coordination access."),
    AccountRoleDefinition("CERTIFYING_ENGINEER", "Certifying Engineer", "OPERATIONAL", "Certifying staff access; scope remains controlled by authorisations."),
    AccountRoleDefinition("CERTIFYING_TECHNICIAN", "Certifying Technician", "OPERATIONAL", "Certifying technician access; scope remains controlled by authorisations."),
    AccountRoleDefinition("TECHNICIAN", "Technician", "OPERATIONAL", "Maintenance technician access."),
    AccountRoleDefinition("QUALITY_INSPECTOR", "Quality Inspector", "OPERATIONAL", "Quality inspection and controlled review access."),
    AccountRoleDefinition(
        "QUALITY_OFFICER",
        "Quality Officer",
        "OPERATIONAL",
        "Assists Head of Quality: finding follow-up, CAR chase, QMS reporting. Not a nominated Head of Quality.",
        aliases=("quality officer", "qo", "quality officer amo", "officer quality"),
        regulated=False,
        can_manage_accounts=False,
    ),
    AccountRoleDefinition("AUDITOR", "Auditor", "OPERATIONAL", "Audit execution access without management approval authority."),
    AccountRoleDefinition(
        "STORES_MANAGER", "Stores Manager", "SUPPORT", "Stores management access.",
        can_have_supervisor=False,
    ),
    AccountRoleDefinition("STORES", "Stores", "SUPPORT", "Stores operational access."),
    AccountRoleDefinition("STOREKEEPER", "Storekeeper", "SUPPORT", "Storekeeping access."),
    AccountRoleDefinition("PROCUREMENT_OFFICER", "Procurement Officer", "SUPPORT", "Procurement operational access."),
    AccountRoleDefinition(
        "FINANCE_MANAGER", "Finance Manager", "SUPPORT", "Tenant-defined finance management access.",
        can_have_supervisor=False,
    ),
    AccountRoleDefinition("ACCOUNTS_OFFICER", "Accounts Officer", "SUPPORT", "Tenant-defined accounts access."),
    AccountRoleDefinition("VIEW_ONLY", "View only", "GENERAL", "Read-only access."),
)

ROLE_DEFINITIONS = {definition.key: definition for definition in _DEFINITIONS}


def _alias_index() -> dict[str, str]:
    result: dict[str, str] = {}
    for definition in _DEFINITIONS:
        for value in (definition.key, definition.label, *definition.aliases):
            token = normalize_role_token(value)
            existing = result.get(token)
            if existing is not None and existing != definition.key:
                raise RuntimeError(f"Account role alias {value!r} is ambiguous")
            result[token] = definition.key
    return result


ROLE_ALIAS_INDEX = _alias_index()
REGULATED_MANAGEMENT_ROLE_KEYS = frozenset(
    definition.key for definition in _DEFINITIONS if definition.regulated
)
ACCOUNT_ADMIN_ROLE_KEYS = frozenset({"SUPERUSER", "AMO_ADMIN"})


def canonical_role_key(value: object) -> str | None:
    if isinstance(value, AccountRole):
        return value.value
    return ROLE_ALIAS_INDEX.get(normalize_role_token(value))


def resolve_account_role(value: object) -> AccountRole:
    key = canonical_role_key(value)
    if key is None:
        raise ValueError(f"Unknown account role or alias: {value!r}")
    return AccountRole.__members__[key]


def infer_regulated_role(position_title: object) -> AccountRole | None:
    key = canonical_role_key(position_title)
    if key not in REGULATED_MANAGEMENT_ROLE_KEYS:
        return None
    return AccountRole.__members__[key]


def role_definition(value: object) -> AccountRoleDefinition:
    role = resolve_account_role(value)
    return ROLE_DEFINITIONS[role.value]


def canonical_position_title(value: object) -> str | None:
    key = canonical_role_key(value)
    definition = ROLE_DEFINITIONS.get(key or "")
    return definition.label if definition and definition.regulated else None


def role_catalogue(*, include_superuser: bool) -> list[AccountRoleDefinition]:
    return [
        definition
        for definition in _DEFINITIONS
        if include_superuser or definition.key != AccountRole.SUPERUSER.value
    ]


def aliases_for(value: object) -> tuple[str, ...]:
    return role_definition(value).aliases


def is_any_role(value: object, allowed: Iterable[object]) -> bool:
    key = canonical_role_key(value)
    return key is not None and key in {canonical_role_key(item) for item in allowed}
