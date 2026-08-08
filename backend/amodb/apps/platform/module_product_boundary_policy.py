from __future__ import annotations

from . import module_commerce


_INSTALLED = False


def install_module_product_boundary_policy() -> None:
    """Reconcile commercial products with the actual application boundaries.

    Technical Records remains embedded in Maintenance Operations because its
    service layer directly consumes work-order/task-card and fleet state. Safety,
    Workshops and Rostering are not separately sellable until they have complete
    entitlement-gated application boundaries. Document Control, by contrast, is
    a complete authenticated regulated workspace and is independently gated.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    quality = module_commerce.FIRST_PARTY_MODULES.get("quality", {})
    embedded = [
        value
        for value in quality.get("embedded_capabilities", [])
        if value != "document_control_legacy"
    ]
    quality["embedded_capabilities"] = embedded

    module_commerce.FIRST_PARTY_MODULES["document_control"] = {
        "name": "Document Control & Publications",
        "description": (
            "Controlled manuals/publications, revisions, temporary revisions, LEP, "
            "distribution, controlled copies, external sources, review and reader governance."
        ),
        "kind": "STANDALONE",
        "hard_requires": [],
        "embedded_capabilities": [
            "controlled_documents",
            "publications",
            "revision_control",
            "temporary_revisions",
            "lep",
            "controlled_distribution",
            "controlled_copies",
            "external_sources",
            "document_reviews",
            "governed_reader",
        ],
        "customer_selectable": True,
        "implemented": True,
        "commercial_note": (
            "Existing Quality customers retain compatibility through the legacy quality entitlement alias; "
            "new document_control subscriptions are independently enforceable."
        ),
    }

    module_commerce.FIRST_PARTY_MODULES["compliance_suite"] = {
        "name": "Compliance Governance Suite",
        "description": "Quality & Compliance, Training & Competence, and Document Control as one governance package.",
        "kind": "BUNDLE",
        "hard_requires": [],
        "included_modules": ["quality", "training", "document_control"],
        "embedded_capabilities": [],
        "customer_selectable": True,
        "implemented": True,
    }

    _INSTALLED = True
