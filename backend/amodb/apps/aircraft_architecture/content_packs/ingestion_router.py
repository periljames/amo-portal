from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from amodb.apps.accounts import models as account_models
from amodb.security import get_current_active_user

from . import ingestion, ingestion_schemas, services


router = APIRouter(prefix="/content-packs/oem-import", tags=["aircraft OEM source import"])


@router.post("/preview", response_model=ingestion_schemas.OemWorkbookPreview)
async def preview_oem_workbook(
    file: UploadFile = File(...),
    user: account_models.User = Depends(get_current_active_user),
):
    services.require_source_contributor(user)
    content = await file.read(ingestion.MAX_SOURCE_BYTES + 1)
    return ingestion.preview_oem_workbook(
        filename=file.filename or "source-workbook",
        content=content,
    )
