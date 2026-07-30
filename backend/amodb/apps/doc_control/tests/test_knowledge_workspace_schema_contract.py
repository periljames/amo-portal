from amodb.apps.doc_control.knowledge_workspace_router import ExecutionProfileUpdate


def test_execution_profile_preserves_external_schema_alias_without_shadowing_base_model():
    payload = ExecutionProfileUpdate.model_validate({
        "execution_type": "PORTAL_FORM",
        "submission_mode": "PORTAL_SUBMISSION",
        "schema": {"type": "object", "properties": {"finding": {"type": "string"}}},
    })

    assert payload.execution_schema["type"] == "object"
    assert payload.model_dump(by_alias=True)["schema"] == payload.execution_schema
    assert "schema" not in ExecutionProfileUpdate.model_fields
