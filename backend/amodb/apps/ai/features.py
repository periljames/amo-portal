from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AIFeatureDefinition:
    code: str
    label: str
    context_kind: str


FEATURES = (
    AIFeatureDefinition("CONNECTIVITY_TEST", "Connectivity test", "administration"),
    AIFeatureDefinition("AUDIT_FINDING_ASSISTANT", "Audit finding assistant", "audit"),
    AIFeatureDefinition("CAPA_DRAFTING", "CAPA drafting", "corrective_action"),
    AIFeatureDefinition("REGULATORY_COMPARISON", "Regulatory comparison", "document"),
    AIFeatureDefinition("MANUAL_REVIEW", "Manual review assistant", "document"),
    AIFeatureDefinition("DOCUMENT_INTELLIGENCE", "Document intelligence", "document"),
    AIFeatureDefinition("CHECKLIST_DRAFTING", "Checklist drafting", "document"),
)

FEATURE_CODES = frozenset(feature.code for feature in FEATURES)
