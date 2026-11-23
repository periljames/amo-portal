from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
from pydantic import ValidationError
import importlib
from amodb.apps.quality import schemas
router = importlib.import_module("amodb.apps.quality.router")

def test_response_section_patch_preserves_existing_description():
    car=SimpleNamespace(id=uuid4())
    attachment=SimpleNamespace(id=uuid4(),car_id=car.id,filename="review.pdf",description="Retained description",response_section=None,content_type="application/pdf",size_bytes=100,sha256=None,uploaded_at=datetime.now(timezone.utc))
    db=MagicMock();db.query.return_value.filter.return_value.first.side_effect=[car,attachment]
    with patch("amodb.apps.quality.car_rca_router.assert_invite_access"), patch.object(router,"_require_public_car_invite_editable"):
        result=router.update_car_invite_attachment("token",attachment.id,schemas.CARAttachmentUpdate(response_section="CONTAINMENT"),db)
    assert result.response_section=="CONTAINMENT"
    assert result.description=="Retained description"
    db.commit.assert_called_once()

@pytest.mark.parametrize("section",["CONTAINMENT","ROOT_CAUSE","CORRECTIVE",None])
def test_response_section_roundtrips_and_does_not_require_a_description(section):
    payload=schemas.CARAttachmentUpdate(response_section=section)
    assert payload.model_dump(exclude_unset=True)=={"response_section":section}

def test_arbitrary_response_section_is_rejected():
    with pytest.raises(ValidationError): schemas.CARAttachmentUpdate(response_section="UNRELATED")

def test_register_uses_linked_finding_level_and_severity_instead_of_car_priority():
    finding=SimpleNamespace(level=router.models.FindingLevel.LEVEL_2,severity=router.models.QMSFindingSeverity.MAJOR,description="Independent verification missing",finding_ref="F-1",audit=SimpleNamespace(id=uuid4(),audit_ref="AUD-1",title="Maintenance control audit"))
    car=SimpleNamespace(finding=finding,requested_by_user_id=None,assigned_to_user_id=None,created_at=datetime.now(timezone.utc),closed_at=None,due_date=None,target_closure_date=None,root_cause_status="PENDING",capa_status="PENDING",evidence_verified_at=None,root_cause_review_note=None,capa_review_note=None,summary="CAR summary",root_cause_text=None,root_cause=None,capa_text=None,corrective_action=None,preventive_action=None,submitted_by_name=None,priority="LOW")
    result=router._decorate_car_register_items(MagicMock(),[car])[0]
    assert result.audit_title=="Maintenance control audit"
    assert result.finding_description=="Independent verification missing"
    assert result.finding_level=="LEVEL 2"
    assert result.finding_severity=="MAJOR"
