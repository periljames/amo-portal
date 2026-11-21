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

@pytest.mark.parametrize("section",["CONTAINMENT","ROOT_CAUSE","CORRECTIVE","PREVENTIVE",None])
def test_response_section_roundtrips_and_does_not_require_a_description(section):
    payload=schemas.CARAttachmentUpdate(response_section=section)
    assert payload.model_dump(exclude_unset=True)=={"response_section":section}

def test_arbitrary_response_section_is_rejected():
    with pytest.raises(ValidationError): schemas.CARAttachmentUpdate(response_section="UNRELATED")
