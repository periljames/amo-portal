"""Tenant access profiles, module grants and organization-role templates.

This module is the bridge between four deliberately separate concepts:

* ``WorkforcePosition``: the approved organization/employment position;
* ``AuthRoleDefinition``: the tenant's editable portal access profile;
* ``User.is_amo_admin``: a tenant-administration overlay; and
* maintenance/licence authorisations: personal regulated privileges.

The stable ``AccountRole`` remains a compatibility persona for existing
workflow guards. A custom profile may rename and narrow that persona, but it
cannot manufacture SUPERUSER authority or a certifying privilege.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from amodb.user_id import generate_user_id

from . import models, role_registry


MODULE_CATALOGUE = (
    ("quality", "Quality & assurance", "Compliance", "Audits, findings, corrective action and management review."),
    ("training", "Training & competence", "Compliance", "Training records, competence, examinations and recurrent planning."),
    ("documents", "Documents & manuals", "Compliance", "Controlled manuals, policies, forms, distribution and retained records."),
    ("safety", "Safety management", "Compliance", "Safety reporting, risk, investigations and safety promotion."),
    ("reliability", "Reliability", "Continuing airworthiness", "Reliability data, programmes, FRACAS and reports."),
    ("planning", "Maintenance planning", "Maintenance", "Forecasting, programmes, work packages and maintenance planning."),
    ("production", "Production control", "Maintenance", "Production control, work execution and operational coordination."),
    ("maintenance", "Maintenance execution", "Maintenance", "Work orders, defects, non-routines, inspections and close-out."),
    ("technical_records", "Technical records", "Maintenance", "Aircraft records, logbooks, packs, traceability and reconciliation."),
    ("rostering", "Workforce & rostering", "People", "Rosters, attendance, leave, qualifications and workforce self-service."),
    ("fleet", "Fleet & aircraft", "Assets", "Aircraft, configurations, induction and utilization."),
    ("stores", "Stores & inventory", "Supply chain", "Stock, tooling, receiving, issuing and inventory control."),
    ("procurement", "Procurement", "Supply chain", "Requests, sourcing, purchase orders and supplier coordination."),
    ("finance", "Finance", "Commercial", "Billing, accounts, financial controls and exports."),
)

MODULE_CODES = frozenset(item[0] for item in MODULE_CATALOGUE)

OPERATIONAL_CAPABILITIES = {
    "doc_control.document.create": ("documents", "Create controlled-document records."),
    "doc_control.revision.publish": ("documents", "Publish a fully approved controlled-document revision."),
    "doc_control.tr.transition": ("documents", "Transition temporary-revision records."),
    "doc_control.transmittal.issue": ("documents", "Issue controlled-document transmittals."),
}

OPERATIONAL_CAPABILITIES_BY_PROFILE = {
    "DOCUMENT_CONTROL_OFFICER": frozenset(OPERATIONAL_CAPABILITIES),
    "QUALITY_MANAGER": frozenset({"doc_control.document.create", "doc_control.revision.publish"}),
    "QUALITY_OFFICER": frozenset({"doc_control.document.create"}),
}

QUALITY_VIEW_CAPABILITIES = frozenset({
    "qms.dashboard.view", "qms.inbox.view", "qms.calendar.view",
    "qms.audit.view", "qms.finding.view", "qms.car.view",
    "qms.document.view", "qms.training.view", "qms.supplier.view",
    "qms.equipment.view", "qms.risk.view", "qms.change.view",
    "qms.management_review.view", "qms.reports.view", "qms.external.view",
    "qms.evidence.view", "qms.evidence.download", "qms.settings.view",
})
QUALITY_ALL_CAPABILITIES = QUALITY_VIEW_CAPABILITIES | frozenset({
    "qms.audit.execute", "qms.audit.manage", "qms.audit.notice.manage",
    "qms.audit.programme.approve", "qms.audit.programme.quality_review",
    "qms.calendar.manage", "qms.finding.create", "qms.car.close",
    "qms.car.issue", "qms.car.manage", "qms.car.reject",
    "qms.car.respond", "qms.car.review", "qms.change.manage",
    "qms.document.approve", "qms.document.archive", "qms.document.create",
    "qms.document.publish", "qms.document.review", "qms.document.revision",
    "qms.equipment.manage", "qms.evidence.archive",
    "qms.management_review.manage", "qms.reports.attest_authority",
    "qms.reports.export", "qms.reports.manage", "qms.risk.manage",
    "qms.settings.manage", "qms.supplier.manage", "qms.training.manage",
})
QUALITY_MANAGER_CAPABILITIES = QUALITY_ALL_CAPABILITIES - frozenset({
    "qms.audit.programme.approve", "qms.reports.attest_authority",
})
QUALITY_OFFICER_CAPABILITIES = QUALITY_VIEW_CAPABILITIES | frozenset({
    "qms.audit.execute", "qms.audit.manage", "qms.audit.notice.manage",
    "qms.calendar.manage", "qms.finding.create", "qms.car.issue",
    "qms.car.manage", "qms.car.respond", "qms.reports.export",
})
QUALITY_AUDITOR_CAPABILITIES = frozenset({
    "qms.dashboard.view", "qms.inbox.view", "qms.calendar.view",
    "qms.audit.view", "qms.audit.execute", "qms.finding.view",
    "qms.finding.create", "qms.car.view", "qms.document.view",
    "qms.evidence.view", "qms.evidence.download",
})
QUALITY_SUPPORT_CAPABILITIES = frozenset({
    "qms.dashboard.view", "qms.inbox.view", "qms.calendar.view",
    "qms.audit.view", "qms.finding.view", "qms.car.view",
    "qms.document.view", "qms.evidence.view", "qms.training.view",
    "qms.reports.view",
})
QUALITY_DOCUMENT_CONTROL_CAPABILITIES = frozenset({
    "qms.dashboard.view", "qms.inbox.view", "qms.document.view",
    "qms.evidence.view", "qms.evidence.download", "qms.training.view",
})
QUALITY_EXECUTIVE_CAPABILITIES = QUALITY_VIEW_CAPABILITIES | frozenset({
    "qms.reports.export", "qms.reports.attest_authority",
    "qms.audit.programme.approve",
})

TRAINING_SELF_CAPABILITIES = frozenset({
    "training.self.view",
    "training.attendance.sign_self",
    "training.certificate.view",
})
TRAINING_READ_CAPABILITIES = TRAINING_SELF_CAPABILITIES | frozenset({
    "training.view", "training.people.view", "training.course.view",
    "training.requirement.view", "training.plan.view", "training.budget.view",
    "training.session.view", "training.attendance.view",
    "training.assessment.view", "training.authorization.view",
    "training.report.view",
})
TRAINING_OFFICER_CAPABILITIES = TRAINING_READ_CAPABILITIES | frozenset({
    "training.people.manage", "training.course.manage",
    "training.requirement.manage", "training.plan.manage",
    "training.budget.manage", "training.session.manage",
    "training.attendance.manage", "training.assessment.create",
    "training.assessment.perform", "training.authorization.prepare",
    "training.certificate.issue", "training.report.export",
})
TRAINING_QUALITY_CAPABILITIES = TRAINING_READ_CAPABILITIES | frozenset({
    "training.plan.review", "training.budget.review", "training.session.close",
    "training.attendance.manage", "training.attendance.correct",
    "training.assessment.create", "training.assessment.perform",
    "training.assessment.review", "training.assessment.approve",
    "training.authorization.prepare", "training.authorization.recommend",
    "training.authorization.committee_decide", "training.certificate.issue",
    "training.certificate.revoke", "training.certificate.reissue",
    "training.report.export",
})
TRAINING_ALL_CAPABILITIES = TRAINING_OFFICER_CAPABILITIES | TRAINING_QUALITY_CAPABILITIES | frozenset({
    "training.plan.approve", "training.budget.approve",
    "training.authorization.issue", "training.authorization.renew",
    "training.authorization.restrict", "training.authorization.withdraw",
    "training.settings.manage",
})

RELIABILITY_ALL_CAPABILITIES = frozenset({
    "reliability.read", "reliability.source.manage", "reliability.ingest",
    "reliability.data_quality.resolve", "reliability.fracas.triage",
    "reliability.fracas.investigate", "reliability.fracas.action",
    "reliability.fracas.verify", "reliability.programme.manage",
    "reliability.programme.approve", "reliability.metric.manage",
    "reliability.metric.execute", "reliability.meeting.manage",
    "reliability.change.manage", "reliability.change.approve",
    "reliability.handoff.manage", "reliability.authority.prepare",
    "reliability.authority.submit", "reliability.ai.use",
    "reliability.ai.review", "reliability.audit.read",
})
RELIABILITY_READ_CAPABILITIES = frozenset({
    "reliability.read", "reliability.audit.read",
})
RELIABILITY_ENGINEER_CAPABILITIES = RELIABILITY_READ_CAPABILITIES | frozenset({
    "reliability.ingest", "reliability.fracas.triage",
    "reliability.fracas.investigate", "reliability.fracas.action",
    "reliability.metric.execute", "reliability.handoff.manage",
    "reliability.ai.use",
})
RELIABILITY_QUALITY_CAPABILITIES = RELIABILITY_ALL_CAPABILITIES - frozenset({
    "reliability.authority.submit",
})
RELIABILITY_EXECUTIVE_CAPABILITIES = RELIABILITY_READ_CAPABILITIES | frozenset({
    "reliability.programme.approve", "reliability.change.approve",
    "reliability.authority.submit",
})

WORKFLOW_CAPABILITIES = {
    **OPERATIONAL_CAPABILITIES,
    **{
        code: ("quality", "Quality workflow authority governed by the assigned tenant access profile.")
        for code in QUALITY_ALL_CAPABILITIES
    },
    **{
        code: ("training", "Training workflow authority governed by the assigned tenant access profile.")
        for code in TRAINING_ALL_CAPABILITIES
    },
    **{
        code: ("reliability", "Reliability workflow authority governed by the assigned tenant access profile.")
        for code in RELIABILITY_ALL_CAPABILITIES
    },
}


def _workflow_capabilities_for_profile(
    *,
    profile_code: str,
    base_role_key: str,
    module_permissions: dict[str, str],
) -> frozenset[str]:
    """Derive specialist workflow grants from stable persona + module level.

    Tenant-facing labels and reporting terminology never participate in this
    decision. A module ``manage`` grant opens operational actions, while the
    stable persona continues to constrain approvals and regulated decisions.
    """
    profile_code = role_registry.normalize_role_token(profile_code)
    base_role_key = role_registry.canonical_role_key(base_role_key) or "USER"
    result: set[str] = set()
    if module_permissions.get("documents") == "manage":
        result.update(OPERATIONAL_CAPABILITIES_BY_PROFILE.get(profile_code, ()))
        if not result:
            for template_code, codes in OPERATIONAL_CAPABILITIES_BY_PROFILE.items():
                template = TEMPLATES_BY_CODE.get(template_code)
                if template and template["base"] == base_role_key:
                    result.update(codes)

    quality_level = module_permissions.get("quality")
    if quality_level:
        if base_role_key == "ACCOUNTABLE_EXECUTIVE":
            result.update(QUALITY_EXECUTIVE_CAPABILITIES)
        elif base_role_key == "QUALITY_MANAGER":
            result.update(QUALITY_MANAGER_CAPABILITIES)
        elif base_role_key == "QUALITY_OFFICER":
            result.update(
                QUALITY_OFFICER_CAPABILITIES
                if quality_level == "manage"
                else QUALITY_VIEW_CAPABILITIES
            )
        elif base_role_key in {"QUALITY_INSPECTOR", "AUDITOR"}:
            result.update(QUALITY_AUDITOR_CAPABILITIES)
        elif base_role_key == "QUALITY_SUPPORT_OFFICER":
            result.update(QUALITY_SUPPORT_CAPABILITIES)
        elif base_role_key == "DOCUMENT_CONTROL_OFFICER":
            result.update(QUALITY_DOCUMENT_CONTROL_CAPABILITIES)
        else:
            result.update(QUALITY_VIEW_CAPABILITIES)

    training_level = module_permissions.get("training")
    if training_level:
        if base_role_key in {"USER", "VIEW_ONLY", "MAINTENANCE_SUPPORT"}:
            result.update(TRAINING_SELF_CAPABILITIES)
        else:
            result.update(TRAINING_READ_CAPABILITIES)
        if training_level == "manage":
            if base_role_key == "QUALITY_MANAGER":
                result.update(TRAINING_ALL_CAPABILITIES)
            elif base_role_key in {"QUALITY_INSPECTOR", "AUDITOR"}:
                result.update(TRAINING_READ_CAPABILITIES)
            elif base_role_key in {"HUMAN_RESOURCES_MANAGER", "HUMAN_RESOURCES_OFFICER"}:
                result.update(TRAINING_READ_CAPABILITIES)
                result.update({
                    "training.people.manage", "training.plan.manage",
                    "training.session.manage", "training.attendance.manage",
                    "training.report.export",
                })
            elif base_role_key in {"FINANCE_MANAGER", "ACCOUNTS_OFFICER"}:
                result.update({
                    "training.budget.view", "training.budget.review",
                    "training.budget.approve", "training.report.view",
                    "training.report.export",
                })
            elif base_role_key != "VIEW_ONLY":
                result.update(TRAINING_OFFICER_CAPABILITIES)

    reliability_level = module_permissions.get("reliability")
    if reliability_level:
        result.update(RELIABILITY_READ_CAPABILITIES)
        if reliability_level == "manage":
            if base_role_key == "QUALITY_MANAGER":
                result.update(RELIABILITY_QUALITY_CAPABILITIES)
            elif base_role_key == "ACCOUNTABLE_EXECUTIVE":
                result.update(RELIABILITY_EXECUTIVE_CAPABILITIES)
            elif base_role_key in {
                "PLANNING_ENGINEER", "PRODUCTION_ENGINEER", "QUALITY_OFFICER",
                "QUALITY_INSPECTOR", "SAFETY_MANAGER", "SAFETY_OFFICER",
            }:
                result.update(RELIABILITY_ENGINEER_CAPABILITIES)
    return frozenset(result)


def _modules(*view: str, manage: Iterable[str] = ()) -> dict[str, str]:
    result = {code: "view" for code in view}
    for code in manage:
        result[code] = "manage"
    return result


# The six prescribed management positions retain their legal titles. All
# supporting positions are reference defaults and their display terminology is
# tenant-editable. A portal profile never grants a licence, inspection stamp or
# certification authorization by itself.
DEFAULT_ACCESS_PROFILE_TEMPLATES = (
    dict(code="ACCOUNTABLE_EXECUTIVE", name="Accountable Executive", base="ACCOUNTABLE_EXECUTIVE", category="KCAR_2025_MANAGEMENT", reports=None, regulated=True, description="Final AMO accountability for resources, safety and effective performance.", modules=_modules(*MODULE_CODES, manage=("quality", "reliability", "rostering"))),
    dict(code="QUALITY_MANAGER", name="Quality Manager", base="QUALITY_MANAGER", category="KCAR_2025_MANAGEMENT", reports="ACCOUNTABLE_EXECUTIVE", regulated=True, description="Independent compliance monitoring and direct reporting to the Accountable Executive.", modules=_modules("quality", "training", "documents", "safety", "reliability", "planning", "production", "maintenance", "technical_records", "rostering", "fleet", "stores", "procurement", manage=("quality", "training", "documents", "reliability", "procurement", "rostering", "fleet"))),
    dict(code="SAFETY_MANAGER", name="Safety Manager", base="SAFETY_MANAGER", category="KCAR_2025_MANAGEMENT", reports="ACCOUNTABLE_EXECUTIVE", regulated=True, description="Implements and maintains the AMO safety management system.", modules=_modules("safety", "quality", "training", "documents", "maintenance", "rostering", "fleet", "reliability", manage=("safety", "fleet", "reliability"))),
    dict(code="BASE_MAINTENANCE_MANAGER", name="Base Maintenance Manager", base="BASE_MAINTENANCE_MANAGER", category="KCAR_2025_MANAGEMENT", reports="ACCOUNTABLE_EXECUTIVE", regulated=True, description="Controls approved base-maintenance activity and resources.", modules=_modules("maintenance", "production", "planning", "technical_records", "training", "documents", "rostering", "fleet", "stores", "procurement", "quality", manage=("maintenance", "production", "technical_records", "rostering", "fleet"))),
    dict(code="LINE_MAINTENANCE_MANAGER", name="Line Maintenance Manager", base="LINE_MAINTENANCE_MANAGER", category="KCAR_2025_MANAGEMENT", reports="ACCOUNTABLE_EXECUTIVE", regulated=True, description="Controls approved line-maintenance activity and resources.", modules=_modules("maintenance", "production", "planning", "technical_records", "training", "documents", "rostering", "fleet", "stores", "procurement", "quality", manage=("maintenance", "production", "technical_records", "rostering", "fleet"))),
    dict(code="WORKSHOP_MANAGER", name="Workshop Manager", base="WORKSHOP_MANAGER", category="KCAR_2025_MANAGEMENT", reports="ACCOUNTABLE_EXECUTIVE", regulated=True, description="Controls approved component-workshop activity and resources.", modules=_modules("maintenance", "production", "planning", "technical_records", "training", "documents", "rostering", "fleet", "stores", "procurement", "quality", manage=("maintenance", "production", "technical_records", "rostering", "fleet"))),
    dict(code="QUALITY_OFFICER", name="Quality Officer", base="QUALITY_OFFICER", category="QUALITY", reports="QUALITY_MANAGER", regulated=False, description="Quality-system preparation and follow-up without Quality Manager approval authority.", modules=_modules("quality", "training", "documents", "rostering", "maintenance", "technical_records", "procurement", "reliability", manage=("quality", "reliability"))),
    dict(code="DOCUMENT_CONTROL_OFFICER", name="Document Control Officer (Librarian)", base="DOCUMENT_CONTROL_OFFICER", category="QUALITY", reports="QUALITY_MANAGER", regulated=False, description="Controls documents, distribution, library custody and retained records.", modules=_modules("documents", "quality", "training", "rostering", manage=("documents",))),
    dict(code="QUALITY_SUPPORT_OFFICER", name="Quality Support Officer", base="QUALITY_SUPPORT_OFFICER", category="QUALITY", reports="QUALITY_MANAGER", regulated=False, description="Administrative quality support without audit, approval or finding-closure authority.", modules=_modules("quality", "training", "documents", "rostering")),
    dict(code="AUDITOR", name="Auditor", base="AUDITOR", category="QUALITY", reports="QUALITY_MANAGER", regulated=False, description="Audit fieldwork access; approval authority remains segregated.", modules=_modules("quality", "training", "documents", "rostering", "maintenance", "technical_records", "stores", "procurement", manage=("quality",))),
    dict(code="QUALITY_INSPECTOR", name="Quality Control Officer / Inspector", base="QUALITY_INSPECTOR", category="QUALITY", reports="QUALITY_MANAGER", regulated=False, description="Inspection persona only; the actual inspection and certification scope remains a separate authorization.", modules=_modules("maintenance", "production", "quality", "training", "documents", "technical_records", "rostering", "procurement", "reliability", manage=("maintenance", "procurement", "reliability"))),
    dict(code="SAFETY_OFFICER", name="Safety Officer", base="SAFETY_OFFICER", category="SAFETY", reports="SAFETY_MANAGER", regulated=False, description="Safety reporting, investigation support and promotion under the Safety Manager.", modules=_modules("safety", "quality", "training", "documents", "rostering", "maintenance", "reliability", manage=("safety", "reliability"))),
    dict(code="SAFETY_CAMPAIGNER", name="Safety Campaigner", base="USER", category="SAFETY", reports="SAFETY_OFFICER", regulated=False, description="Safety-promotion participation with employee self-service access.", modules=_modules("safety", "training", "documents", "rostering")),
    dict(code="LINE_MAINTENANCE_SUPERVISOR", name="Line Maintenance Supervisor", base="MAINTENANCE_SUPERVISOR", category="LINE_MAINTENANCE", reports="LINE_MAINTENANCE_MANAGER", regulated=False, description="Supervises line-maintenance personnel within assigned department and station scope.", modules=_modules("maintenance", "production", "planning", "technical_records", "training", "documents", "rostering", "fleet", "stores", "quality", manage=("maintenance", "production", "rostering"))),
    dict(code="LINE_QUALITY_CONTROL_OFFICER", name="Line Quality Control Officer", base="QUALITY_INSPECTOR", category="LINE_MAINTENANCE", reports="LINE_MAINTENANCE_MANAGER", regulated=False, description="Performs assigned line quality-control inspections; certification requires separate authorization.", modules=_modules("maintenance", "production", "quality", "training", "documents", "technical_records", "rostering", manage=("maintenance",))),
    dict(code="HANGAR_SUPERVISOR", name="Hangar Supervisor", base="MAINTENANCE_SUPERVISOR", category="BASE_MAINTENANCE", reports="BASE_MAINTENANCE_MANAGER", regulated=False, description="Supervises hangar personnel within assigned scope.", modules=_modules("maintenance", "production", "planning", "technical_records", "training", "documents", "rostering", "fleet", "stores", "quality", manage=("maintenance", "production", "rostering"))),
    dict(code="HANGAR_QUALITY_CONTROL_OFFICER", name="Hangar Quality Control Officer", base="QUALITY_INSPECTOR", category="BASE_MAINTENANCE", reports="BASE_MAINTENANCE_MANAGER", regulated=False, description="Performs assigned hangar quality-control inspections; certification requires separate authorization.", modules=_modules("maintenance", "production", "quality", "training", "documents", "technical_records", "rostering", manage=("maintenance",))),
    dict(code="WORKSHOP_QUALITY_CONTROL_OFFICER", name="Workshop Quality Control Officer", base="QUALITY_INSPECTOR", category="WORKSHOP", reports="WORKSHOP_MANAGER", regulated=False, description="Performs assigned component-workshop inspections within separately authorized scope.", modules=_modules("maintenance", "production", "quality", "training", "documents", "technical_records", "rostering", manage=("maintenance",))),
    dict(code="STORES_SUPERVISOR", name="Stores Supervisor", base="STORES_MANAGER", category="BASE_MAINTENANCE", reports="BASE_MAINTENANCE_MANAGER", regulated=False, description="Supervises stores and procurement-clerk activity.", modules=_modules("stores", "procurement", "maintenance", "production", "training", "documents", "rostering", manage=("stores", "procurement", "rostering"))),
    dict(code="TECHNICAL_RECORDS_PLANNING_SUPERVISOR", name="Technical Records & Planning Supervisor", base="TECHNICAL_RECORDS_SUPERVISOR", category="BASE_MAINTENANCE", reports="BASE_MAINTENANCE_MANAGER", regulated=False, description="Supervises technical-records custody and planning coordination.", modules=_modules("technical_records", "planning", "production", "maintenance", "training", "documents", "rostering", "fleet", manage=("technical_records", "planning", "rostering"))),
    dict(code="TECHNICAL_RECORDS_OFFICER", name="Technical Records Officer (TRO)", base="TECHNICAL_RECORDS_OFFICER", category="TECHNICAL_RECORDS", reports="TECHNICAL_RECORDS_PLANNING_SUPERVISOR", regulated=False, description="Maintains aircraft technical records, logbooks and controlled record packs.", modules=_modules("technical_records", "planning", "production", "maintenance", "training", "documents", "rostering", "fleet", manage=("technical_records",))),
    dict(code="CERTIFYING_ENGINEER", name="Line Certifying Engineer", base="CERTIFYING_ENGINEER", category="LINE_MAINTENANCE", reports="LINE_MAINTENANCE_SUPERVISOR", regulated=False, description="Line-maintenance execution persona; licence and company authorization determine certification scope.", modules=_modules("maintenance", "production", "technical_records", "training", "documents", "rostering", "fleet", "stores", "procurement", manage=("maintenance", "production", "technical_records", "fleet", "procurement"))),
    dict(code="LINE_CERTIFYING_TECHNICIAN", name="Line Certifying Technician", base="CERTIFYING_TECHNICIAN", category="LINE_MAINTENANCE", reports="LINE_MAINTENANCE_SUPERVISOR", regulated=False, description="Line-maintenance execution persona; company authorization determines certification scope.", modules=_modules("maintenance", "production", "technical_records", "training", "documents", "rostering", "fleet", "stores", "procurement", manage=("maintenance", "production", "technical_records", "fleet", "procurement"))),
    dict(code="HANGAR_CERTIFYING_ENGINEER", name="Hangar Certifying Engineer", base="CERTIFYING_ENGINEER", category="BASE_MAINTENANCE", reports="HANGAR_SUPERVISOR", regulated=False, description="Base-maintenance execution persona; licence and company authorization determine certification scope.", modules=_modules("maintenance", "production", "technical_records", "training", "documents", "rostering", "fleet", "stores", "procurement", manage=("maintenance", "production", "technical_records", "fleet", "procurement"))),
    dict(code="CERTIFYING_TECHNICIAN", name="Hangar Certifying Technician", base="CERTIFYING_TECHNICIAN", category="BASE_MAINTENANCE", reports="HANGAR_SUPERVISOR", regulated=False, description="Base-maintenance execution persona; company authorization determines certification scope.", modules=_modules("maintenance", "production", "technical_records", "training", "documents", "rostering", "fleet", "stores", "procurement", manage=("maintenance", "production", "technical_records", "fleet", "procurement"))),
    dict(code="TECHNICIAN", name="Hangar Technician", base="TECHNICIAN", category="BASE_MAINTENANCE", reports="HANGAR_SUPERVISOR", regulated=False, description="Performs hangar maintenance tasks within assigned competence and supervision.", modules=_modules("maintenance", "production", "training", "documents", "rostering", "fleet", "stores", manage=("maintenance", "production", "fleet"))),
    dict(code="WORKSHOP_SPECIALIST", name="Workshop Repair Specialist (Tenant-defined)", base="TECHNICIAN", category="WORKSHOP", reports="WORKSHOP_QUALITY_CONTROL_OFFICER", regulated=False, description="Tenant-editable specialist profile for an approved workshop capability area.", modules=_modules("maintenance", "production", "training", "documents", "rostering", "stores", manage=("maintenance", "production"))),
    dict(code="SHEET_METAL_COMPOSITES_REPAIR_SPECIALIST", name="Sheet Metal & Composites Repair Specialist", base="TECHNICIAN", category="WORKSHOP", reports="WORKSHOP_QUALITY_CONTROL_OFFICER", regulated=False, description="Performs sheet-metal and composite repair within the approved workshop capability and personal competence.", modules=_modules("maintenance", "production", "training", "documents", "rostering", "stores", manage=("maintenance", "production"))),
    dict(code="WHEELS_BRAKES_REPAIR_SPECIALIST", name="Wheels & Brakes Repair Specialist", base="TECHNICIAN", category="WORKSHOP", reports="WORKSHOP_QUALITY_CONTROL_OFFICER", regulated=False, description="Performs wheel and brake repair within the approved workshop capability and personal competence.", modules=_modules("maintenance", "production", "training", "documents", "rostering", "stores", manage=("maintenance", "production"))),
    dict(code="BATTERY_SHOP_SERVICE_SPECIALIST", name="Battery Shop Service Specialist", base="TECHNICIAN", category="WORKSHOP", reports="WORKSHOP_QUALITY_CONTROL_OFFICER", regulated=False, description="Performs battery-shop service within the approved workshop capability and personal competence.", modules=_modules("maintenance", "production", "training", "documents", "rostering", "stores", manage=("maintenance", "production"))),
    dict(code="GROUND_EQUIPMENT_TECHNICIAN", name="Ground Equipment Operator / Technician", base="TECHNICIAN", category="LINE_MAINTENANCE", reports="LINE_MAINTENANCE_SUPERVISOR", regulated=False, description="Ground-equipment operation and maintenance within assigned competence.", modules=_modules("maintenance", "production", "training", "documents", "rostering", "stores", manage=("maintenance",))),
    dict(code="AIRCRAFT_GROOMER", name="Aircraft Groomer", base="MAINTENANCE_SUPPORT", category="LINE_MAINTENANCE", reports="LINE_MAINTENANCE_SUPERVISOR", regulated=False, description="Limited maintenance-support and workforce self-service profile.", modules=_modules("maintenance", "training", "documents", "rostering")),
    dict(code="STORES_PROCUREMENT_CLERK", name="Stores & Procurement Clerk", base="STOREKEEPER", category="SUPPLY_CHAIN", reports="STORES_SUPERVISOR", regulated=False, description="Operational stores custody and procurement coordination.", modules=_modules("stores", "procurement", "maintenance", "production", "training", "documents", "rostering", manage=("stores", "procurement"))),
    dict(code="PLANNING_ENGINEER", name="Planning Engineer", base="PLANNING_ENGINEER", category="PLANNING", reports="TECHNICAL_RECORDS_PLANNING_SUPERVISOR", regulated=False, description="Maintenance forecasting and work-package planning.", modules=_modules("planning", "technical_records", "maintenance", "production", "training", "documents", "rostering", "fleet", "stores", "procurement", "reliability", manage=("planning", "technical_records", "procurement", "reliability", "rostering", "fleet"))),
    dict(code="PRODUCTION_ENGINEER", name="Production Engineer", base="PRODUCTION_ENGINEER", category="PRODUCTION", reports="BASE_MAINTENANCE_MANAGER", regulated=False, description="Production coordination and maintenance execution oversight.", modules=_modules("production", "maintenance", "planning", "technical_records", "training", "documents", "rostering", "fleet", "stores", "procurement", "reliability", manage=("production", "maintenance", "technical_records", "procurement", "reliability", "rostering", "fleet"))),
    dict(code="PROCUREMENT_OFFICER", name="Procurement Officer", base="PROCUREMENT_OFFICER", category="SUPPLY_CHAIN", reports="STORES_SUPERVISOR", regulated=False, description="Procurement operations and supplier coordination.", modules=_modules("procurement", "stores", "maintenance", "training", "documents", "rostering", manage=("procurement",))),
    dict(code="FINANCE_MANAGER", name="Finance Manager", base="FINANCE_MANAGER", category="SUPPORT", reports="ACCOUNTABLE_EXECUTIVE", regulated=False, description="Tenant finance management and controlled exports.", modules=_modules("finance", "procurement", "stores", "rostering", manage=("finance", "procurement"))),
    dict(code="ACCOUNTS_OFFICER", name="Accounts Officer", base="ACCOUNTS_OFFICER", category="SUPPORT", reports="FINANCE_MANAGER", regulated=False, description="Tenant accounts processing within assigned scope.", modules=_modules("finance", "procurement", "rostering", manage=("finance", "procurement"))),
    dict(code="HUMAN_RESOURCES_MANAGER", name="Human Resources Manager", base="HUMAN_RESOURCES_MANAGER", category="SUPPORT", reports="ACCOUNTABLE_EXECUTIVE", regulated=False, description="Manages tenant workforce records, employment lifecycle and organization structures without inheriting tenant-administrator authority.", modules=_modules("training", "documents", "rostering", manage=("training", "rostering"))),
    dict(code="HUMAN_RESOURCES_OFFICER", name="Human Resources Officer", base="HUMAN_RESOURCES_OFFICER", category="SUPPORT", reports="HUMAN_RESOURCES_MANAGER", regulated=False, description="Maintains workforce records and employee services within governed HR workflows.", modules=_modules("training", "documents", "rostering", manage=("training", "rostering"))),
    dict(code="GENERAL_USER", name="General User", base="USER", category="GENERAL", reports=None, regulated=False, description="Employee self-service with no operational module authority by default.", modules=_modules("training", "documents", "rostering")),
    dict(code="VIEW_ONLY", name="Read-only User", base="VIEW_ONLY", category="GENERAL", reports=None, regulated=False, description="Read-only access to expressly assigned modules.", modules=_modules("training", "documents", "rostering")),
)

TEMPLATES_BY_CODE = {item["code"]: item for item in DEFAULT_ACCESS_PROFILE_TEMPLATES}


def _capability_code(module_code: str, level: str) -> str:
    return f"portal.{module_code}.{level}"


def ensure_capability_catalogue(db: Session) -> dict[str, models.AuthCapabilityDefinition]:
    expected: dict[str, tuple[str, str]] = {}
    for code, label, _category, description in MODULE_CATALOGUE:
        expected[_capability_code(code, "view")] = (code, f"View {label}. {description}")
        expected[_capability_code(code, "manage")] = (code, f"Manage {label}. Server workflow authority still applies.")
    expected.update(WORKFLOW_CAPABILITIES)
    existing = {
        row.code: row
        for row in db.query(models.AuthCapabilityDefinition).filter(
            models.AuthCapabilityDefinition.code.in_(list(expected))
        ).all()
    }
    for code, (module, description) in expected.items():
        if code in existing:
            continue
        row = models.AuthCapabilityDefinition(
            id=generate_user_id(), code=code, module=module, description=description
        )
        db.add(row)
        existing[code] = row
    db.flush()
    return existing


def _set_profile_capabilities(
    db: Session,
    *,
    profile: models.AuthRoleDefinition,
    module_permissions: dict[str, str],
    catalogue: dict[str, models.AuthCapabilityDefinition] | None = None,
    operational_capabilities: Iterable[str] | None = None,
) -> None:
    catalogue = catalogue or ensure_capability_catalogue(db)
    unknown_modules = sorted(set(module_permissions) - MODULE_CODES)
    if unknown_modules:
        raise ValueError(
            "Unknown portal module(s): " + ", ".join(unknown_modules)
        )
    invalid_levels = sorted(
        f"{module_code}={level}"
        for module_code, level in module_permissions.items()
        if level not in {"view", "manage"}
    )
    if invalid_levels:
        raise ValueError(
            "Module access must be 'view' or 'manage': " + ", ".join(invalid_levels)
        )
    desired_codes: set[str] = set()
    for module_code, level in module_permissions.items():
        desired_codes.add(_capability_code(module_code, "view"))
        if level == "manage":
            desired_codes.add(_capability_code(module_code, "manage"))
    if operational_capabilities is not None:
        desired_codes.update(code for code in operational_capabilities if code in WORKFLOW_CAPABILITIES)
    portal_bindings = [
        item for item in profile.capabilities
        if item.capability and (
            item.capability.code.startswith("portal.")
            or (
                operational_capabilities is not None
                and item.capability.code in WORKFLOW_CAPABILITIES
            )
        )
    ]
    for binding in portal_bindings:
        if binding.capability.code not in desired_codes:
            db.delete(binding)
    existing_codes = {
        item.capability.code for item in portal_bindings
        if item.capability and item.capability.code in desired_codes
    }
    for code in sorted(desired_codes - existing_codes):
        db.add(models.AuthRoleCapabilityBinding(
            id=generate_user_id(), role_id=profile.id,
            capability_id=catalogue[code].id, constraints_json={},
        ))
    db.flush()


def ensure_tenant_access_profiles(db: Session, *, amo_id: str) -> dict[str, int]:
    catalogue = ensure_capability_catalogue(db)
    existing = {
        row.tenant_code: row
        for row in db.query(models.AuthRoleDefinition).filter(
            models.AuthRoleDefinition.amo_id == amo_id
        ).options(selectinload(models.AuthRoleDefinition.capabilities)).all()
        if row.tenant_code
    }
    created = 0
    repaired = 0
    for template in DEFAULT_ACCESS_PROFILE_TEMPLATES:
        row = existing.get(template["code"])
        if row is None:
            row = models.AuthRoleDefinition(
                id=generate_user_id(),
                code=f"TENANT:{amo_id}:{template['code']}",
                scope_type="TENANT",
                amo_id=amo_id,
                tenant_code=template["code"],
                display_name=template["name"],
                base_role_key=template["base"],
                category=template["category"],
                reports_to_role_code=template["reports"],
                description=template["description"],
                is_system=True,
                is_regulated=bool(template["regulated"]),
                is_editable=not bool(template["regulated"]),
                is_active=True,
            )
            db.add(row)
            db.flush()
            _set_profile_capabilities(
                db,
                profile=row,
                module_permissions=template["modules"],
                catalogue=catalogue,
                operational_capabilities=_workflow_capabilities_for_profile(
                    profile_code=template["code"],
                    base_role_key=template["base"],
                    module_permissions=template["modules"],
                ),
            )
            existing[template["code"]] = row
            created += 1
            continue
        # Supporting roles are tenant-editable: reconciliation must not undo
        # their terminology, functional grouping or reporting line. The stable
        # persona is always repaired; the legal topology is additionally
        # protected only for prescribed management roles.
        protected = {
            "base_role_key": template["base"],
            "is_regulated": bool(template["regulated"]),
            "is_editable": not bool(template["regulated"]),
        }
        if template["regulated"]:
            protected.update({
                "display_name": template["name"],
                "category": template["category"],
                "reports_to_role_code": template["reports"],
                "description": template["description"],
                "is_active": True,
            })
        if any(getattr(row, key) != value for key, value in protected.items()):
            for key, value in protected.items():
                setattr(row, key, value)
            repaired += 1
        current_module_permissions = (
            template["modules"]
            if template["regulated"]
            else profile_module_permissions(row)
        )
        before_codes = {
            binding.capability.code
            for binding in row.capabilities
            if binding.capability is not None
        }
        desired_workflow_codes = _workflow_capabilities_for_profile(
            profile_code=str(row.tenant_code or template["code"]),
            base_role_key=str(row.base_role_key or template["base"]),
            module_permissions=current_module_permissions,
        )
        _set_profile_capabilities(
            db,
            profile=row,
            module_permissions=current_module_permissions,
            catalogue=catalogue,
            operational_capabilities=desired_workflow_codes,
        )
        if (before_codes & set(WORKFLOW_CAPABILITIES)) != set(desired_workflow_codes):
            repaired += 1
    db.flush()
    assigned = 0
    users = db.query(models.User).filter(
        models.User.amo_id == amo_id,
        models.User.is_superuser.is_(False),
    ).all()
    now = datetime.now(timezone.utc)
    for user in users:
        current = db.query(models.AuthUserRoleAssignment.id).filter(
            models.AuthUserRoleAssignment.amo_id == amo_id,
            models.AuthUserRoleAssignment.user_id == user.id,
            models.AuthUserRoleAssignment.is_primary.is_(True),
            or_(
                models.AuthUserRoleAssignment.valid_from.is_(None),
                models.AuthUserRoleAssignment.valid_from <= now,
            ),
            or_(
                models.AuthUserRoleAssignment.valid_to.is_(None),
                models.AuthUserRoleAssignment.valid_to >= now,
            ),
        ).first()
        if current is not None:
            continue
        try:
            if assign_default_profile_for_role(db, user=user) is not None:
                assigned += 1
        except ValueError:
            # A regulated account may already have a governed Workforce
            # placement whose profile link is repaired later in the same
            # organization-framework initialization. Do not abort the whole
            # tenant bootstrap or bypass that placement/profile consistency.
            continue
    db.flush()
    return {"created": created, "repaired": repaired, "assigned": assigned, "total": len(existing)}


def _active_assignment_query(db: Session, *, amo_id: str, user_id: str):
    now = datetime.now(timezone.utc)
    return db.query(models.AuthUserRoleAssignment).join(
        models.AuthRoleDefinition,
        models.AuthRoleDefinition.id == models.AuthUserRoleAssignment.role_id,
    ).filter(
        models.AuthUserRoleAssignment.amo_id == amo_id,
        models.AuthUserRoleAssignment.user_id == user_id,
        or_(models.AuthUserRoleAssignment.valid_from.is_(None), models.AuthUserRoleAssignment.valid_from <= now),
        or_(models.AuthUserRoleAssignment.valid_to.is_(None), models.AuthUserRoleAssignment.valid_to >= now),
        models.AuthRoleDefinition.is_active.is_(True),
    )


def primary_access_profile(db: Session, *, user: models.User) -> models.AuthRoleDefinition | None:
    assignment = _active_assignment_query(
        db, amo_id=str(user.amo_id), user_id=str(user.id)
    ).filter(models.AuthUserRoleAssignment.is_primary.is_(True)).options(
        selectinload(models.AuthUserRoleAssignment.role).selectinload(models.AuthRoleDefinition.capabilities)
    ).order_by(models.AuthUserRoleAssignment.created_at.desc()).first()
    return assignment.role if assignment else None


def primary_access_profiles_for_users(
    db: Session,
    *,
    amo_id: str,
    user_ids: Iterable[str],
) -> dict[str, models.AuthRoleDefinition]:
    ids = {str(value) for value in user_ids if value}
    if not ids:
        return {}
    now = datetime.now(timezone.utc)
    rows = db.query(models.AuthUserRoleAssignment).join(
        models.AuthRoleDefinition,
        models.AuthRoleDefinition.id == models.AuthUserRoleAssignment.role_id,
    ).filter(
        models.AuthUserRoleAssignment.amo_id == amo_id,
        models.AuthUserRoleAssignment.user_id.in_(ids),
        models.AuthUserRoleAssignment.is_primary.is_(True),
        or_(models.AuthUserRoleAssignment.valid_from.is_(None), models.AuthUserRoleAssignment.valid_from <= now),
        or_(models.AuthUserRoleAssignment.valid_to.is_(None), models.AuthUserRoleAssignment.valid_to >= now),
        models.AuthRoleDefinition.is_active.is_(True),
    ).options(
        selectinload(models.AuthUserRoleAssignment.role)
    ).order_by(
        models.AuthUserRoleAssignment.created_at.desc(),
        models.AuthUserRoleAssignment.id.desc(),
    ).all()
    result: dict[str, models.AuthRoleDefinition] = {}
    for assignment in rows:
        result.setdefault(str(assignment.user_id), assignment.role)
    return result


def assign_primary_access_profile(
    db: Session,
    *,
    user: models.User,
    profile_id: str,
    actor_user_id: str | None,
) -> models.AuthRoleDefinition:
    if user.is_superuser:
        raise ValueError("Platform superusers cannot receive tenant access profiles")
    profile = db.query(models.AuthRoleDefinition).filter(
        models.AuthRoleDefinition.id == profile_id,
        models.AuthRoleDefinition.amo_id == user.amo_id,
        models.AuthRoleDefinition.is_active.is_(True),
    ).with_for_update().first()
    if profile is None:
        raise ValueError("Access profile not found in this tenant")
    if profile.base_role_key in {"SUPERUSER", "AMO_ADMIN", None}:
        raise ValueError("Platform and tenant administration are not assignable access profiles")
    try:
        base_role = role_registry.resolve_account_role(profile.base_role_key)
    except ValueError as exc:
        raise ValueError("Access profile has an invalid base persona") from exc

    # A governed Workforce placement is the source of truth for the person's
    # organisational position. Account administration must not silently put a
    # different portal profile over that approved position.
    from amodb.apps.workforce import governance_models
    today = date.today()
    governed_position = db.query(governance_models.WorkforcePosition).join(
        governance_models.WorkforcePersonPlacement,
        governance_models.WorkforcePersonPlacement.position_id
        == governance_models.WorkforcePosition.id,
    ).filter(
        governance_models.WorkforcePersonPlacement.amo_id == user.amo_id,
        governance_models.WorkforcePersonPlacement.user_id == user.id,
        governance_models.WorkforcePersonPlacement.placement_type == "PRIMARY",
        governance_models.WorkforcePersonPlacement.effective_from <= today,
        or_(
            governance_models.WorkforcePersonPlacement.effective_to.is_(None),
            governance_models.WorkforcePersonPlacement.effective_to >= today,
        ),
        governance_models.WorkforcePosition.amo_id == user.amo_id,
        governance_models.WorkforcePosition.is_active.is_(True),
    ).order_by(
        governance_models.WorkforcePersonPlacement.effective_from.desc(),
        governance_models.WorkforcePersonPlacement.created_at.desc(),
    ).first()
    governed_profile_id = str(governed_position.access_profile_id) if (
        governed_position is not None and governed_position.access_profile_id
    ) else None
    if profile.is_regulated and (
        governed_position is None or governed_profile_id != str(profile.id)
    ):
        raise ValueError(
            "Assign the prescribed management position in Workforce before applying its access profile"
        )
    if governed_profile_id and governed_profile_id != str(profile.id):
        raise ValueError(
            "This user is governed by an active Workforce position; change the position or its linked access profile in Workforce"
        )

    now = datetime.now(timezone.utc)
    assignments = db.query(models.AuthUserRoleAssignment).filter(
        models.AuthUserRoleAssignment.amo_id == user.amo_id,
        models.AuthUserRoleAssignment.user_id == user.id,
        models.AuthUserRoleAssignment.is_primary.is_(True),
        models.AuthUserRoleAssignment.valid_to.is_(None),
    ).with_for_update().all()
    matching = next(
        (
            row for row in assignments
            if row.role_id == profile.id
            and (row.valid_from is None or row.valid_from <= now)
        ),
        None,
    )
    for row in assignments:
        if row is not matching:
            row.valid_to = row.valid_from if row.valid_from and row.valid_from > now else now
    if matching is None:
        matching = models.AuthUserRoleAssignment(
            id=generate_user_id(), amo_id=user.amo_id, user_id=user.id,
            role_id=profile.id, department_id=user.department_id,
            assigned_by_user_id=actor_user_id, is_primary=True, valid_from=now,
        )
        db.add(matching)
    else:
        matching.department_id = user.department_id
        matching.assigned_by_user_id = actor_user_id
        matching.valid_to = None
    user.role = base_role
    # Portal access never grants personal audit authority. The legacy boolean is
    # deliberately not changed here; governed, scoped QMS People privileges and
    # the audit's participant assignments are the authoritative controls.
    db.flush()
    return profile


def assign_default_profile_for_role(
    db: Session,
    *,
    user: models.User,
    actor_user_id: str | None = None,
) -> models.AuthRoleDefinition | None:
    if user.is_superuser:
        return None
    role_key = role_registry.canonical_role_key(user.role) or "USER"
    preferred_code = "GENERAL_USER" if role_key == "USER" else role_key
    profile = db.query(models.AuthRoleDefinition).filter(
        models.AuthRoleDefinition.amo_id == user.amo_id,
        models.AuthRoleDefinition.tenant_code == preferred_code,
        models.AuthRoleDefinition.is_active.is_(True),
    ).first()
    if profile is None:
        profile = db.query(models.AuthRoleDefinition).filter(
            models.AuthRoleDefinition.amo_id == user.amo_id,
            models.AuthRoleDefinition.base_role_key == role_key,
            models.AuthRoleDefinition.is_active.is_(True),
        ).order_by(models.AuthRoleDefinition.is_system.desc(), models.AuthRoleDefinition.display_name.asc()).first()
    if profile is None and role_key == "AMO_ADMIN":
        profile = db.query(models.AuthRoleDefinition).filter(
            models.AuthRoleDefinition.amo_id == user.amo_id,
            models.AuthRoleDefinition.tenant_code == "GENERAL_USER",
            models.AuthRoleDefinition.is_active.is_(True),
        ).first()
    if profile is None:
        return None
    return assign_primary_access_profile(
        db, user=user, profile_id=str(profile.id), actor_user_id=actor_user_id
    )


def capability_codes_for_user(db: Session, *, user: models.User) -> list[str]:
    if user.is_superuser:
        return sorted(
            _capability_code(module_code, "view")
            for module_code in MODULE_CODES
        )
    assignments = _active_assignment_query(
        db, amo_id=str(user.amo_id), user_id=str(user.id)
    ).filter(models.AuthUserRoleAssignment.is_primary.is_(True))
    has_primary = assignments.first() is not None
    rows = assignments.join(
        models.AuthRoleCapabilityBinding,
        models.AuthRoleCapabilityBinding.role_id == models.AuthUserRoleAssignment.role_id,
    ).join(
        models.AuthCapabilityDefinition,
        models.AuthCapabilityDefinition.id == models.AuthRoleCapabilityBinding.capability_id,
    ).with_entities(models.AuthCapabilityDefinition.code).distinct().all()
    codes = {str(row[0]) for row in rows}
    if not has_primary:
        role_key = role_registry.canonical_role_key(user.role) or "USER"
        template = TEMPLATES_BY_CODE.get("GENERAL_USER" if role_key == "USER" else role_key)
        if template is None:
            template = next(
                (item for item in DEFAULT_ACCESS_PROFILE_TEMPLATES if item["base"] == role_key),
                TEMPLATES_BY_CODE["GENERAL_USER"],
            )
        for module_code, level in template["modules"].items():
            codes.add(_capability_code(module_code, "view"))
            if level == "manage":
                codes.add(_capability_code(module_code, "manage"))
        codes.update(_workflow_capabilities_for_profile(
            profile_code=template["code"],
            base_role_key=template["base"],
            module_permissions=template["modules"],
        ))
    return sorted(codes)


def module_access_from_capabilities(capability_codes: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for capability in capability_codes:
        parts = str(capability).split(".")
        if len(parts) != 3 or parts[0] != "portal" or parts[1] not in MODULE_CODES:
            continue
        level = parts[2]
        if level == "manage" or (level == "view" and parts[1] not in result):
            result[parts[1]] = level
    return result


def attach_user_access(db: Session, user: models.User) -> models.User:
    if user.is_superuser:
        profile = None
        capabilities = capability_codes_for_user(db, user=user)
        display_name = "Platform superuser"
    else:
        profile = primary_access_profile(db, user=user)
        capabilities = capability_codes_for_user(db, user=user)
        display_name = profile.display_name if profile else role_registry.role_definition(user.role).label
    setattr(user, "access_profile_id", str(profile.id) if profile else None)
    setattr(user, "access_profile_name", display_name)
    setattr(user, "capability_codes", capabilities)
    setattr(user, "module_access", module_access_from_capabilities(capabilities))
    return user


def user_has_capability(db: Session, *, user: models.User, capability_code: str) -> bool:
    capabilities = capability_codes_for_user(db, user=user)
    if capability_code in capabilities:
        return True
    return False


def _validated_reporting_profile(
    db: Session,
    *,
    amo_id: str,
    reports_to_role_code: str | None,
    current_profile_id: str | None = None,
) -> models.AuthRoleDefinition | None:
    parent_code = role_registry.normalize_role_token(reports_to_role_code)
    if not parent_code:
        return None
    parent = db.query(models.AuthRoleDefinition).filter(
        models.AuthRoleDefinition.amo_id == amo_id,
        models.AuthRoleDefinition.tenant_code == parent_code,
        models.AuthRoleDefinition.is_active.is_(True),
    ).first()
    if parent is None:
        raise ValueError("The selected reporting profile does not exist in this tenant")
    if current_profile_id and str(parent.id) == str(current_profile_id):
        raise ValueError("An access profile cannot report to itself")
    seen = {str(current_profile_id)} if current_profile_id else set()
    current = parent
    while current is not None:
        current_id = str(current.id)
        if current_id in seen:
            raise ValueError("The reporting profile would create a cycle")
        seen.add(current_id)
        next_code = role_registry.normalize_role_token(current.reports_to_role_code)
        if not next_code:
            break
        current = db.query(models.AuthRoleDefinition).filter(
            models.AuthRoleDefinition.amo_id == amo_id,
            models.AuthRoleDefinition.tenant_code == next_code,
            models.AuthRoleDefinition.is_active.is_(True),
        ).first()
        if current is None:
            raise ValueError("An existing reporting profile points to an unavailable parent")
    return parent


def profile_module_permissions(profile: models.AuthRoleDefinition) -> dict[str, str]:
    return module_access_from_capabilities(
        binding.capability.code
        for binding in profile.capabilities
        if binding.capability is not None
    )


def profile_assignment_count(db: Session, *, profile_id: str) -> int:
    now = datetime.now(timezone.utc)
    return int(db.query(models.AuthUserRoleAssignment).filter(
        models.AuthUserRoleAssignment.role_id == profile_id,
        models.AuthUserRoleAssignment.is_primary.is_(True),
        or_(
            models.AuthUserRoleAssignment.valid_from.is_(None),
            models.AuthUserRoleAssignment.valid_from <= now,
        ),
        or_(
            models.AuthUserRoleAssignment.valid_to.is_(None),
            models.AuthUserRoleAssignment.valid_to >= now,
        ),
    ).count())


def create_access_profile(
    db: Session,
    *,
    amo_id: str,
    tenant_code: str,
    display_name: str,
    base_role_key: str,
    category: str,
    description: str | None,
    reports_to_role_code: str | None,
    module_permissions: dict[str, str],
    actor_user_id: str,
) -> models.AuthRoleDefinition:
    code = role_registry.normalize_role_token(tenant_code)
    if not code:
        raise ValueError("Role code is required")
    if not display_name.strip():
        raise ValueError("Display name is required")
    if base_role_key in {"SUPERUSER", "AMO_ADMIN"}:
        raise ValueError("Administration is assigned separately from operational access")
    persona = role_registry.resolve_account_role(base_role_key)
    if persona in {models.AccountRole.SUPERUSER, models.AccountRole.AMO_ADMIN}:
        raise ValueError("Administration is assigned separately from operational access")
    if role_registry.role_definition(persona).regulated:
        raise ValueError(
            "Prescribed management personas cannot be cloned or renamed; use the protected framework profile"
        )
    if db.query(models.AuthRoleDefinition.id).filter(
        models.AuthRoleDefinition.amo_id == amo_id,
        models.AuthRoleDefinition.tenant_code == code,
    ).first():
        raise ValueError("Role code is already in use in this tenant")
    parent = _validated_reporting_profile(
        db, amo_id=amo_id, reports_to_role_code=reports_to_role_code
    )
    profile = models.AuthRoleDefinition(
        id=generate_user_id(), code=f"TENANT:{amo_id}:{code}", scope_type="TENANT",
        amo_id=amo_id, tenant_code=code, display_name=display_name.strip(),
        base_role_key=persona.value, category=category.strip().upper() or "CUSTOM",
        reports_to_role_code=parent.tenant_code if parent else None,
        description=(description or "").strip() or None,
        is_system=False, is_regulated=False, is_editable=True, is_active=True,
        updated_by_user_id=actor_user_id,
    )
    db.add(profile)
    db.flush()
    _set_profile_capabilities(
        db,
        profile=profile,
        module_permissions=module_permissions,
        operational_capabilities=_workflow_capabilities_for_profile(
            profile_code=code,
            base_role_key=persona.value,
            module_permissions=module_permissions,
        ),
    )
    return profile


def update_access_profile(
    db: Session,
    *,
    profile: models.AuthRoleDefinition,
    display_name: str | None,
    description: str | None,
    category: str | None,
    reports_to_role_code: str | None,
    base_role_key: str | None,
    module_permissions: dict[str, str] | None,
    is_active: bool | None,
    expected_version: int,
    actor_user_id: str,
    update_fields: set[str] | None = None,
) -> models.AuthRoleDefinition:
    update_fields = update_fields or set()
    if profile.version != expected_version:
        raise ValueError("This access profile changed; refresh before saving")
    if profile.is_regulated:
        if display_name is not None and display_name.strip() != profile.display_name:
            raise ValueError("The prescribed management title is protected")
        if base_role_key is not None and base_role_key != profile.base_role_key:
            raise ValueError("The prescribed management persona is protected")
        if "reports_to_role_code" in update_fields and reports_to_role_code != profile.reports_to_role_code:
            raise ValueError("The prescribed management reporting line is protected")
        if category is not None and category.strip().upper() != str(profile.category or "").upper():
            raise ValueError("The prescribed management category is protected")
        if "description" in update_fields and (description or "").strip() != (profile.description or "").strip():
            raise ValueError("The prescribed management responsibilities are protected")
        if module_permissions is not None and module_permissions != profile_module_permissions(profile):
            raise ValueError("The prescribed management module boundary is protected")
        if is_active is False:
            raise ValueError("A prescribed management profile cannot be deactivated")
    if base_role_key is not None:
        # The base persona is a security identity used by legacy workflow
        # guards. Allowing it to change in-place would leave every existing
        # assignment and Workforce-position link carrying stale authority.
        # Terminology and module boundaries remain editable; a genuinely new
        # persona mapping must be created as a new profile and reassigned.
        if base_role_key != profile.base_role_key:
            raise ValueError("An access profile's stable persona cannot be changed; create a new profile instead")
        if base_role_key in {"SUPERUSER", "AMO_ADMIN"}:
            raise ValueError("Administration is assigned separately from operational access")
        persona = role_registry.resolve_account_role(base_role_key)
        if not profile.is_regulated and role_registry.role_definition(persona).regulated:
            raise ValueError("A custom profile cannot inherit a prescribed management persona")
        profile.base_role_key = base_role_key
    if display_name is not None:
        if not display_name.strip():
            raise ValueError("Display name is required")
        profile.display_name = display_name.strip()
    if "description" in update_fields:
        profile.description = (description or "").strip() or None
    if category is not None:
        profile.category = category.strip().upper() or "CUSTOM"
    if "reports_to_role_code" in update_fields:
        parent = _validated_reporting_profile(
            db,
            amo_id=str(profile.amo_id),
            reports_to_role_code=reports_to_role_code,
            current_profile_id=str(profile.id),
        )
        profile.reports_to_role_code = parent.tenant_code if parent else None
    if is_active is not None:
        if not is_active:
            if profile_assignment_count(db, profile_id=str(profile.id)):
                raise ValueError("Reassign users before deactivating this access profile")
            # Keep the governed organization chart and the access catalogue in
            # lockstep. A position may not silently retain an inactive profile,
            # nor may an active child report to a deactivated parent profile.
            from amodb.apps.workforce import governance_models
            linked_position = db.query(governance_models.WorkforcePosition.id).filter(
                governance_models.WorkforcePosition.amo_id == profile.amo_id,
                governance_models.WorkforcePosition.access_profile_id == profile.id,
                governance_models.WorkforcePosition.is_active.is_(True),
            ).first()
            if linked_position is not None:
                raise ValueError("Relink active Workforce positions before deactivating this access profile")
            reporting_child = db.query(models.AuthRoleDefinition.id).filter(
                models.AuthRoleDefinition.amo_id == profile.amo_id,
                models.AuthRoleDefinition.reports_to_role_code == profile.tenant_code,
                models.AuthRoleDefinition.is_active.is_(True),
            ).first()
            if reporting_child is not None:
                raise ValueError("Reassign active reporting roles before deactivating this access profile")
        profile.is_active = is_active
    if module_permissions is not None:
        _set_profile_capabilities(
            db,
            profile=profile,
            module_permissions=module_permissions,
            operational_capabilities=_workflow_capabilities_for_profile(
                profile_code=str(profile.tenant_code or ""),
                base_role_key=str(profile.base_role_key),
                module_permissions=module_permissions,
            ),
        )
    profile.version += 1
    profile.updated_by_user_id = actor_user_id
    profile.updated_at = datetime.now(timezone.utc)
    db.flush()
    return profile
