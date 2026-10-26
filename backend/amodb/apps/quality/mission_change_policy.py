"""Required readiness evidence for controlled changes (MOPM 1.9 / 1.10)."""

CONTROLLED_CHANGE_TYPES = {"CAPABILITY_CHANGE", "LINE_STATION", "REGULATORY_TRANSITION", "PROCEDURE_CHANGE"}

CHANGE_GATE_TEMPLATE = (
    {"gate_code": "CHANGE_SCOPE", "title": "Change scope and approval impact", "category": "Scope", "requirement_ref": "MOPM 1.9.1–1.9.2", "source_owner_module": "quality", "source_type": "CHANGE_ASSESSMENT", "sort_order": 10},
    {"gate_code": "SAFETY_ASSESSMENT", "title": "Safety assessment and mitigations", "category": "Safety", "requirement_ref": "MOPM 2.18.11; SMS Manual", "source_owner_module": "safety", "source_type": "RISK_ASSESSMENT", "sort_order": 20},
    {"gate_code": "CONTROLLED_DOCUMENTS", "title": "Controlled procedure and document revisions", "category": "Documents", "requirement_ref": "MOPM 1.10; 2.8", "source_owner_module": "document-control", "source_type": "DOCUMENT", "sort_order": 30},
    {"gate_code": "PERSONNEL_READINESS", "title": "Personnel, training and resource readiness", "category": "People", "requirement_ref": "MOPM 1.9.2; 3.4–3.5", "source_owner_module": "people", "source_type": "PERSONNEL_COVERAGE", "sort_order": 40},
    {"gate_code": "AUTHORITY_REQUIREMENTS", "title": "Authority notification, approval and operating conditions assessment", "category": "Authority", "requirement_ref": "MOPM 1.9.1–1.9.3", "source_owner_module": "quality", "source_type": "AUTHORITY_REQUIREMENTS", "sort_order": 50},
)


def mission_gate_template(mission_type, capability_template):
    if mission_type == "CAPABILITY_ADDITION":
        return capability_template
    if mission_type in CONTROLLED_CHANGE_TYPES:
        return CHANGE_GATE_TEMPLATE
    return ()
