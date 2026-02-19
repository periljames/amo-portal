from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from amodb.apps.accounts.models import AMO, AMOAsset, AMOAssetKind

router = APIRouter(prefix="/api/tenants", tags=["Manuals Branding"], dependencies=[Depends(get_current_active_user)])


@router.get("/{tenant_slug}/branding")
def get_tenant_branding(tenant_slug: str, db: Session = Depends(get_db)):
    amo = db.query(AMO).filter(AMO.login_slug == tenant_slug).first()
    if not amo:
        raise HTTPException(status_code=404, detail="Tenant not found")

    logo = (
        db.query(AMOAsset)
        .filter(AMOAsset.amo_id == amo.id, AMOAsset.kind == AMOAssetKind.CRS_LOGO, AMOAsset.is_active.is_(True))
        .order_by(AMOAsset.created_at.desc())
        .first()
    )

    logo_url = f"/accounts/amo-assets/{logo.id}/download" if logo else None
    return {
        "tenantSlug": tenant_slug,
        "preferredName": amo.name,
        "logoUrl": logo_url,
        "faviconUrl": None,
        "accentColor": "#0EA5E9",
        "accentColor2": "#6366F1",
        "themeDefault": "light",
        "reader": {
            "paperColor": "#FFFFFF",
            "inkColor": "#0F172A",
            "bgColor": "#F1F5F9",
            "headerStyle": "blur",
            "headerBlur": True,
            "cornerRadius": "lg",
            "density": "comfortable",
        },
    }
