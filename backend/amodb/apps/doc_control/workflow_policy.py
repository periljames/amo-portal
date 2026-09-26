from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DocumentLifecyclePolicy:
    code: str
    technical_review: bool
    quality_review: bool
    accountable_approval: bool
    authority_approval: bool
    controlled_release: bool
    acknowledgement: bool
    rationale: str


def _type(profile: Any, manual: Any) -> str:
    metadata = dict(getattr(profile, "metadata_json", None) or {})
    value = metadata.get("document_type_override") or getattr(manual, "manual_type", None) or "MANUAL"
    return str(value).strip().upper().replace(" ", "_")


def resolve_document_lifecycle_policy(profile: Any, manual: Any) -> DocumentLifecyclePolicy:
    """Resolve a conservative default lifecycle without pretending one route fits all documents.

    Defaults are deliberately based on the document's control purpose. A governed
    metadata override may make a route more restrictive or identify an independent
    audit-tool route, but cannot switch off an explicit regulatory/Authority flag.
    """
    metadata = dict(getattr(profile, "metadata_json", None) or {})
    document_type = _type(profile, manual)
    purpose = str(metadata.get("control_purpose") or "").strip().upper()
    regulated = bool(getattr(profile, "regulated_flag", False))
    authority = bool(getattr(profile, "requires_authority_approval", False))

    if document_type == "RECORD":
        base = DocumentLifecyclePolicy("RECORD_CAPTURE", False, False, False, False, False, False,
            "Records are retained evidence, not publications awaiting a generic approval chain.")
    elif document_type in {"REGULATION", "EXTERNAL_DOCUMENT"}:
        base = DocumentLifecyclePolicy("EXTERNAL_SOURCE_CONTROL", False, False, False, False, True, False,
            "External controlled information is registered, verified for currency and released without inventing internal authorship approval.")
    elif document_type == "CHECKLIST" and purpose in {"AUDIT", "QUALITY_AUDIT", "INTERNAL_AUDIT", "COMPLIANCE_AUDIT"}:
        base = DocumentLifecyclePolicy("INDEPENDENT_AUDIT_TOOL", True, False, False, False, True, False,
            "Audit working tools use an independent audit-owner review route; routine Quality or accountable approval is not forced.")
    elif document_type in {"FORM", "CHECKLIST", "REGISTER"}:
        base = DocumentLifecyclePolicy("FUNCTIONAL_CONTROL", True, False, False, False, True, False,
            "Operational support documents require functional ownership and controlled release, not automatically the full manual chain.")
    elif document_type in {"WORK_INSTRUCTION"}:
        base = DocumentLifecyclePolicy("FUNCTIONAL_PLUS_QUALITY", True, True, False, False, True, False,
            "Work instructions receive functional and Quality review by default; accountable approval is added only where governance requires it.")
    else:
        base = DocumentLifecyclePolicy("GOVERNED_PUBLICATION", True, True, True, authority, True,
            bool(getattr(profile, "acknowledgement_required", False)),
            "Manuals, policies and procedures use the governed publication route unless a documented policy says otherwise.")

    # Regulatory classification can only add gates to the default route.
    quality = base.quality_review or regulated
    accountable = base.accountable_approval or regulated or authority
    authority_required = base.authority_approval or authority
    acknowledgement = base.acknowledgement or bool(getattr(profile, "acknowledgement_required", False))

    return DocumentLifecyclePolicy(
        base.code,
        base.technical_review,
        quality,
        accountable,
        authority_required,
        base.controlled_release,
        acknowledgement,
        base.rationale,
    )


def serialize_document_lifecycle_policy(policy: DocumentLifecyclePolicy) -> dict[str, Any]:
    return {
        "code": policy.code,
        "technical_review": policy.technical_review,
        "quality_review": policy.quality_review,
        "accountable_approval": policy.accountable_approval,
        "authority_approval": policy.authority_approval,
        "controlled_release": policy.controlled_release,
        "acknowledgement": policy.acknowledgement,
        "rationale": policy.rationale,
    }
