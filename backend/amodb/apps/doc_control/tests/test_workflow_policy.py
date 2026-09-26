from types import SimpleNamespace

from amodb.apps.doc_control.workflow_policy import resolve_document_lifecycle_policy


def profile(**kwargs):
    defaults = {
        "metadata_json": {},
        "regulated_flag": False,
        "requires_authority_approval": False,
        "acknowledgement_required": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def manual(document_type: str):
    return SimpleNamespace(manual_type=document_type)


def test_audit_checklist_preserves_independent_audit_route():
    policy = resolve_document_lifecycle_policy(
        profile(metadata_json={"document_type_override": "CHECKLIST", "control_purpose": "INTERNAL_AUDIT"}),
        manual("CHECKLIST"),
    )
    assert policy.code == "INDEPENDENT_AUDIT_TOOL"
    assert policy.technical_review is True
    assert policy.quality_review is False
    assert policy.accountable_approval is False
    assert policy.authority_approval is False


def test_operational_checklist_is_not_forced_through_full_manual_chain():
    policy = resolve_document_lifecycle_policy(profile(), manual("CHECKLIST"))
    assert policy.code == "FUNCTIONAL_CONTROL"
    assert policy.technical_review is True
    assert policy.quality_review is False
    assert policy.accountable_approval is False


def test_regulatory_flag_can_only_add_governance_gates():
    policy = resolve_document_lifecycle_policy(
        profile(regulated_flag=True, metadata_json={"document_type_override": "CHECKLIST", "control_purpose": "INTERNAL_AUDIT"}),
        manual("CHECKLIST"),
    )
    assert policy.quality_review is True
    assert policy.accountable_approval is True


def test_authority_flag_cannot_be_bypassed_by_document_type():
    policy = resolve_document_lifecycle_policy(
        profile(requires_authority_approval=True),
        manual("FORM"),
    )
    assert policy.accountable_approval is True
    assert policy.authority_approval is True


def test_records_are_capture_and_retention_not_publication_workflows():
    policy = resolve_document_lifecycle_policy(profile(), manual("RECORD"))
    assert policy.code == "RECORD_CAPTURE"
    assert policy.controlled_release is False
    assert policy.technical_review is False
    assert policy.quality_review is False
    assert policy.accountable_approval is False
