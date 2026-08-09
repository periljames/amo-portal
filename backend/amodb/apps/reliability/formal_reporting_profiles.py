from __future__ import annotations

from datetime import date
from typing import Any

from .formal_reporting_models import RegulatoryObligation, RequirementAssessmentStatus


PROFILE_VERSION = "2026-08-07.1"
COMMON_SOURCE_CODES = [
    "AU", "AI", "FI", "PM", "OOS", "RM", "SM", "SR", "SB", "CS", "AS", "UR",
    "STRUCTURES", "RECURRING", "ECTM", "ADD",
]
FORMAL_SECTIONS: list[dict[str, Any]] = [
    {"code": "document_control", "title": "Document control", "required": True},
    {"code": "executive_assessment", "title": "Executive Reliability assessment", "required": True},
    {"code": "fleet_composition", "title": "Fleet composition and status", "required": True},
    {"code": "utilisation", "title": "Utilisation", "required": True},
    {"code": "dispatch_reliability", "title": "Dispatch reliability", "required": True},
    {"code": "operational_interruptions", "title": "Operational interruptions", "required": True},
    {"code": "pilot_maintenance_reports", "title": "Pilot and maintenance reports", "required": True},
    {"code": "recurring_defects", "title": "Recurring/repetitive defects", "required": True},
    {"code": "scheduled_findings", "title": "Scheduled maintenance findings", "required": True},
    {"code": "structural_reliability", "title": "Structural reliability", "required": True},
    {"code": "component_reliability", "title": "Component reliability", "required": True},
    {"code": "shop_reports", "title": "Shop reports", "required": True},
    {"code": "propulsion_health", "title": "Engine/APU/propeller health", "required": True},
    {"code": "deferred_defects", "title": "Deferred defects / MEL / CDL", "required": True},
    {"code": "service_bulletins", "title": "Service Bulletins and modifications", "required": True},
    {"code": "cost_performance", "title": "Cost/performance", "required": False},
    {"code": "statistical_analysis", "title": "Statistical analysis", "required": True},
    {"code": "alert_exceedances", "title": "Alert exceedances", "required": True},
    {"code": "fracas", "title": "FRACAS / corrective action", "required": True},
    {"code": "maintenance_programme_effectiveness", "title": "Maintenance Programme effectiveness", "required": True},
    {"code": "management_decisions", "title": "Management decisions", "required": True},
    {"code": "data_quality", "title": "Data-quality statement", "required": True},
    {"code": "conclusions", "title": "Conclusions and recommendations", "required": True},
    {"code": "appendices", "title": "Appendices and evidence index", "required": True},
]

ANALYSIS_ROLES = {
    "SUPERUSER", "AMO_ADMIN", "QUALITY_MANAGER", "SAFETY_MANAGER",
    "PLANNING_ENGINEER", "PRODUCTION_ENGINEER", "QUALITY_INSPECTOR", "AUDITOR",
}
TECHNICAL_REVIEW_ROLES = {
    "SUPERUSER", "AMO_ADMIN", "QUALITY_MANAGER", "PLANNING_ENGINEER", "PRODUCTION_ENGINEER",
}
QUALITY_REVIEW_ROLES = {"SUPERUSER", "AMO_ADMIN", "QUALITY_MANAGER", "QUALITY_INSPECTOR"}
APPROVAL_ROLES = {"SUPERUSER", "AMO_ADMIN", "QUALITY_MANAGER"}
PROFILE_ADMIN_ROLES = {"SUPERUSER", "AMO_ADMIN", "QUALITY_MANAGER"}

COMMON_APPROVAL_WORKFLOW = {
    "separation_of_duties": True,
    "technical_review_roles": sorted(TECHNICAL_REVIEW_ROLES),
    "quality_review_roles": sorted(QUALITY_REVIEW_ROLES),
    "approval_roles": sorted(APPROVAL_ROLES),
}
COMMON_PUBLICATION_RULES = {
    "block_mandatory_gap": True,
    "block_unexplained_withheld": True,
    "require_frozen_effectivity": True,
    "require_data_cutoff": True,
    "require_calculation_snapshot": True,
    "require_source_manifest": True,
    "require_html_hash": True,
    "require_pdf_hash": True,
    "exception_override_requires_governed_record": True,
}


def _req(
    key: str,
    *,
    authority: str,
    jurisdiction: str,
    source_kind: str,
    source_reference: str,
    paragraph_reference: str | None,
    source_url: str,
    revision: str,
    summary: str,
    obligation: RegulatoryObligation,
    section: str,
    sources: list[str] | None = None,
    minimum_months: int | None = None,
    history_months: int | None = None,
    default_status: RequirementAssessmentStatus | None = None,
    publication_blocking: bool | None = None,
    applicability: dict[str, Any] | None = None,
    effective_date: date | None = None,
    reviewer_notes: str | None = None,
) -> dict[str, Any]:
    if default_status is None:
        default_status = RequirementAssessmentStatus.GAP if obligation == RegulatoryObligation.MANDATORY else RequirementAssessmentStatus.WITHHELD
    if publication_blocking is None:
        publication_blocking = obligation == RegulatoryObligation.MANDATORY
    return {
        "requirement_key": key,
        "authority": authority,
        "jurisdiction": jurisdiction,
        "source_kind": source_kind,
        "source_reference": source_reference,
        "paragraph_reference": paragraph_reference,
        "source_url": source_url,
        "effective_date": effective_date,
        "revision": revision,
        "controlled_summary": summary,
        "obligation_status": obligation.value,
        "report_section_code": section,
        "data_source_codes": sources or [],
        "minimum_analysis_months": minimum_months,
        "historical_comparison_months": history_months,
        "applicability_rule": applicability or {"default_applicable": True},
        "evidence_rule": {"default_status": default_status.value},
        "completeness_rule": {"publication_blocking": publication_blocking},
        "reviewer_notes": reviewer_notes,
    }


def profile_definitions() -> list[dict[str, Any]]:
    kcaa_url = "https://www.kcaa.or.ke/legislation-publications/regulations-2025"
    kcaa_ac_url = "https://www.kcaa.or.ke/legislation-publications/advisory-circulars"
    easa_url = "https://www.easa.europa.eu/en/document-library/easy-access-rules/easy-access-rules-continuing-airworthiness"
    faa_url = "https://www.faa.gov/regulations_policies/advisory_circulars/index.cfm/go/document.information/documentid/1035253"
    return [
        {
            "code": "KCAA",
            "name": "KCAA Reliability Programme",
            "authority": "KCAA",
            "jurisdiction": "Kenya",
            "effective_date": None,
            "revision": "KCARs 2025 baseline / legacy AC cross-reference",
            "required_sections": FORMAL_SECTIONS,
            "mandatory_kpis": ["flight_hours", "flight_cycles", "dispatch_reliability_pct", "event_rate_per_100_fh"],
            "minimum_analysis_periods": {"periodic_report": 1, "long_term_trend": 12},
            "statistical_methods": ["mean", "standard_deviation", "alert_limits", "rolling_average", "rates"],
            "historical_windows": [12, 24, 36],
            "source_manifest": [
                {"kind": "REGULATION_INDEX", "reference": "KCAA Regulations 2025", "url": kcaa_url, "accessed": "2026-08-07"},
                {"kind": "ADVISORY_CIRCULAR", "reference": "CAA-AC-AWS010D Reliability Programme", "url": kcaa_ac_url, "effective_date": "2018-07-01", "legacy_regulatory_basis": True, "accessed": "2026-08-07"},
            ],
            "requirements": [
                _req(
                    "KCAA-CURRENT-REGULATORY-MAPPING",
                    authority="KCAA", jurisdiction="Kenya", source_kind="REGULATION",
                    source_reference="Kenya Civil Aviation Regulations 2025 / accepted operator Reliability Programme",
                    paragraph_reference=None, source_url=kcaa_url, revision="2025-current-verification",
                    summary="Verify and record the exact current KCARs 2025 and accepted operator-programme references governing Reliability before a KCAA-profile publication is represented as complete.",
                    obligation=RegulatoryObligation.MANDATORY, section="document_control",
                    applicability={"manual_verification_required": True, "default_applicable": True},
                    reviewer_notes="CAA-AC-AWS010D is retained as legacy/advisory analytical guidance and does not by itself satisfy this requirement.",
                ),
                _req(
                    "KCAA-AWS010D-PERIODIC-REPORT-CONTENT",
                    authority="KCAA", jurisdiction="Kenya", source_kind="ADVISORY_CIRCULAR",
                    source_reference="CAA-AC-AWS010D Reliability Programme", paragraph_reference="Periodic reliability reporting guidance",
                    source_url=kcaa_ac_url, revision="D", effective_date=date(2018, 7, 1),
                    summary="Periodic reporting should present fleet/utilisation information, operational interruptions, dispatch reliability/trends and relevant corrective-action information.",
                    obligation=RegulatoryObligation.ADVISORY, section="executive_assessment", sources=COMMON_SOURCE_CODES,
                    minimum_months=1, history_months=12, applicability={"legacy_guidance": True, "profile_review_required": True},
                ),
                _req(
                    "KCAA-AWS010D-LONG-TERM-TREND",
                    authority="KCAA", jurisdiction="Kenya", source_kind="ADVISORY_CIRCULAR",
                    source_reference="CAA-AC-AWS010D Reliability Programme", paragraph_reference="Periodic report long-term trend guidance",
                    source_url=kcaa_ac_url, revision="D", effective_date=date(2018, 7, 1),
                    summary="Retain long-term trend displays, including 12-consecutive-month examples where applicable.",
                    obligation=RegulatoryObligation.ADVISORY, section="statistical_analysis", sources=COMMON_SOURCE_CODES,
                    minimum_months=12, history_months=12, applicability={"legacy_guidance": True},
                ),
            ],
        },
        {
            "code": "EASA",
            "name": "EASA Continuing Airworthiness Reliability Profile",
            "authority": "EASA",
            "jurisdiction": "European Union",
            "effective_date": None,
            "revision": "Easy Access Rules for Continuing Airworthiness — September 2025",
            "required_sections": FORMAL_SECTIONS,
            "mandatory_kpis": ["flight_hours", "flight_cycles", "event_rate_per_100_fh"],
            "minimum_analysis_periods": {"effectiveness_review": 1},
            "statistical_methods": ["performance_standards", "alert_levels", "trends", "rates", "repetitive_defect_analysis"],
            "historical_windows": [12, 24, 36],
            "source_manifest": [{"kind": "EASY_ACCESS_RULES", "reference": "Regulation (EU) No 1321/2014, Part-M/Part-CAMO AMC/GM", "url": easa_url, "revision": "September 2025", "accessed": "2026-08-07"}],
            "requirements": [
                _req(
                    "EASA-MA302-APPLICABILITY-AND-AMP-CONTROL",
                    authority="EASA", jurisdiction="European Union", source_kind="REGULATION_AMC_GM",
                    source_reference="Regulation (EU) No 1321/2014 — M.A.302 / Appendix I to AMC M.A.302",
                    paragraph_reference="M.A.302 and Appendix I applicability provisions", source_url=easa_url, revision="September 2025",
                    summary="Determine Reliability Programme applicability from the approved maintenance-programme basis and retain the controlled link between in-service experience, programme effectiveness and AMP changes.",
                    obligation=RegulatoryObligation.MANDATORY, section="maintenance_programme_effectiveness", sources=COMMON_SOURCE_CODES,
                    applicability={"manual_applicability_review_required": True, "default_applicable": True},
                ),
                _req(
                    "EASA-AMC-MA302-DATA-ANALYSIS-CORRECTIVE-ACTION",
                    authority="EASA", jurisdiction="European Union", source_kind="AMC_GM", source_reference="Appendix I to AMC M.A.302",
                    paragraph_reference="6.5.1–6.5.7", source_url=easa_url, revision="September 2025",
                    summary="Support controlled data collection/display, trend/repetitive-defect analysis, corrective action and effectiveness evaluation where the Reliability Programme applies.",
                    obligation=RegulatoryObligation.ADVISORY, section="fracas", sources=COMMON_SOURCE_CODES, minimum_months=1, history_months=12,
                    applicability={"when_reliability_programme_applicable": True},
                ),
                _req(
                    "EASA-AMC-MA302-REPORTING-EFFECTIVENESS",
                    authority="EASA", jurisdiction="European Union", source_kind="AMC_GM", source_reference="Appendix I to AMC M.A.302",
                    paragraph_reference="6.5.8–6.5.11", source_url=easa_url, revision="September 2025",
                    summary="Define organisational responsibility, report content/distribution, continuous effectiveness review and controlled approval of maintenance-programme amendments.",
                    obligation=RegulatoryObligation.ADVISORY, section="maintenance_programme_effectiveness", sources=COMMON_SOURCE_CODES,
                    minimum_months=1, history_months=12, applicability={"when_reliability_programme_applicable": True},
                ),
            ],
        },
        {
            "code": "FAA",
            "name": "FAA Reliability Programme Profile",
            "authority": "FAA",
            "jurisdiction": "United States",
            "effective_date": date(2026, 7, 9),
            "revision": "AC 120-17B Editorial Update 2026-07-09",
            "required_sections": FORMAL_SECTIONS,
            "mandatory_kpis": ["flight_hours", "flight_cycles", "event_rate_per_100_fh"],
            "minimum_analysis_periods": {"routine_reporting": 1},
            "statistical_methods": ["performance_standards", "alert_levels", "trends", "rates", "event_based_methods"],
            "historical_windows": [12, 24, 36],
            "source_manifest": [{"kind": "ADVISORY_CIRCULAR", "reference": "AC 120-17B", "url": faa_url, "original_date": "2018-12-19", "editorial_update": "2026-07-09", "accessed": "2026-08-07"}],
            "requirements": [
                _req(
                    "FAA-CFR-OPSPECS-APPLICABILITY",
                    authority="FAA", jurisdiction="United States", source_kind="REGULATION_OPSPECS",
                    source_reference="14 CFR / operator OpSpecs reliability-programme authority",
                    paragraph_reference="Applicable 14 CFR and OpSpecs/MSpec provisions", source_url=faa_url, revision="tenant-current-verification",
                    summary="Verify the operator's current 14 CFR applicability and Reliability Programme OpSpecs/MSpec authority, including permitted scope and restrictions for task/interval adjustment.",
                    obligation=RegulatoryObligation.MANDATORY, section="document_control",
                    applicability={"manual_operator_authority_verification_required": True, "default_applicable": True},
                ),
                _req(
                    "FAA-AC12017B-PROGRAMME-ELEMENTS",
                    authority="FAA", jurisdiction="United States", source_kind="ADVISORY_CIRCULAR", source_reference="AC 120-17B",
                    paragraph_reference="Chapters 3–7", source_url=faa_url, revision="B / Editorial Update 2026-07-09", effective_date=date(2018, 12, 19),
                    summary="Define data collection, performance standards, analysis/recommendation, approval/implementation and reporting/display with controlled data quality and corrective-action follow-up.",
                    obligation=RegulatoryObligation.ADVISORY, section="executive_assessment", sources=COMMON_SOURCE_CODES, minimum_months=1, history_months=12,
                    applicability={"when_ac_method_selected": True},
                ),
                _req(
                    "FAA-AC12017B-REPORTING-DISPLAY",
                    authority="FAA", jurisdiction="United States", source_kind="ADVISORY_CIRCULAR", source_reference="AC 120-17B",
                    paragraph_reference="Chapter 7", source_url=faa_url, revision="B / Editorial Update 2026-07-09", effective_date=date(2018, 12, 19),
                    summary="Reporting/display should portray the operation, identify adverse trends, carry unresolved deficiencies and corrective action, show recommendations and support effectiveness monitoring.",
                    obligation=RegulatoryObligation.ADVISORY, section="statistical_analysis", sources=COMMON_SOURCE_CODES, minimum_months=1, history_months=12,
                    applicability={"when_ac_method_selected": True},
                ),
            ],
        },
        {
            "code": "OPERATOR",
            "name": "Operator Controlled Reliability Programme",
            "authority": "OPERATOR",
            "jurisdiction": "Tenant controlled",
            "effective_date": None,
            "revision": "1",
            "required_sections": FORMAL_SECTIONS,
            "mandatory_kpis": [],
            "minimum_analysis_periods": {},
            "statistical_methods": [],
            "historical_windows": [12, 24, 36],
            "source_manifest": [{"kind": "TENANT_CONTROLLED_DOCUMENT", "reference": "Accepted/approved operator Reliability Programme", "requires_tenant_configuration": True}],
            "requirements": [
                _req(
                    "OPERATOR-PROGRAMME-MAPPING",
                    authority="OPERATOR", jurisdiction="Tenant controlled", source_kind="TENANT_CONTROLLED_DOCUMENT",
                    source_reference="Accepted/approved operator Reliability Programme", paragraph_reference=None, source_url="about:blank", revision="tenant-current",
                    summary="Map the tenant's accepted/approved Reliability Programme requirements, report cycle, analysis methods, approval chain and authority conditions before publication under an OPERATOR profile.",
                    obligation=RegulatoryObligation.MANDATORY, section="document_control", applicability={"manual_configuration_required": True, "default_applicable": True},
                )
            ],
        },
    ]
