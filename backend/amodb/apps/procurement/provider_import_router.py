"""Controlled workbook staging. PROSPECTIVE status blocks use despite an enabled master record."""
from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import date, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from openpyxl import load_workbook
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as accounts
from amodb.apps.quality.tenant_security import set_postgres_tenant_context
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user, require_roles
from . import models, service

router = APIRouter(
    prefix="/api/maintenance/{amo_code}/procurement",
    tags=["external provider import"],
    dependencies=[Depends(require_module("finance_inventory"))],
)
_EDIT = (accounts.AccountRole.PROCUREMENT_OFFICER, accounts.AccountRole.STORES_MANAGER)
_COLUMNS = {
    "supplier_code": ("supplier code", "vendor code", "vendor id", "supplier id", "code"),
    "legal_name": ("supplier name", "vendor name", "provider name", "company name", "name"),
    "trading_name": ("trading name",),
    "email": ("email", "email address"),
    "phone": ("phone", "telephone"),
    "country": ("country",),
    "physical_address": ("address", "physical address"),
}
_MAX_BYTES = 10 * 1024 * 1024

def _tenant(db, amo_code, user):
    tenant = service.resolve_tenant_amo_id(db, amo_code=amo_code, current_user=user)
    set_postgres_tenant_context(db, amo_id=tenant, user_id=str(user.id))
    return tenant

def _key(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

def _value(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value).strip() or None

def _mapping(headers, overrides):
    mapping = {}
    for field, aliases in _COLUMNS.items():
        allowed = {_key(value) for value in (*aliases, overrides.get(field, ""))}
        for index, header in enumerate(headers):
            if _key(header) in allowed:
                mapping[field] = index
                break
    return mapping

@router.post("/external-provider-imports/preview", status_code=201)
async def preview(amo_code: str, file: UploadFile = File(...), mapping_json: str = Form("{}"),
                  db: Session = Depends(get_db),
                  user: accounts.User = Depends(require_roles(*_EDIT))):
    tenant = _tenant(db, amo_code, user)
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(415, "Only XLSX and XLSM files are supported.")
    try:
        overrides = json.loads(mapping_json)
        if not isinstance(overrides, dict) or any(
            key not in _COLUMNS or not isinstance(value, str)
            for key, value in overrides.items()
        ):
            raise ValueError()
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Invalid source column mapping.") from exc
    data = await file.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise HTTPException(413, "Workbook exceeds 10 MB.")
    digest = hashlib.sha256(data).hexdigest()
    existing = db.execute(text("""SELECT id, status FROM external_provider_import_batches
        WHERE amo_id=:amo AND source_sha256=:digest"""),
        {"amo":tenant,"digest":digest}).mappings().first()
    if existing:
        return {"batch_id":existing["id"],"source_sha256":digest,
                "status":existing["status"],"already_uploaded":True}
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=False)
    except Exception as exc:
        raise HTTPException(422, "Cannot open workbook.") from exc
    batch_id = str(uuid4())
    counts = {"total": 0, "ready": 0, "errors": 0, "duplicates": 0}
    try:
        db.execute(text("""INSERT INTO external_provider_import_batches
            (id, amo_id, filename, source_sha256, mapping_json, created_by_user_id)
            VALUES (:id, :amo, :filename, :digest, :mapping, :actor)"""),
            {"id": batch_id, "amo": tenant, "filename": filename[:255],
             "digest": digest, "mapping":json.dumps(overrides), "actor": str(user.id)})
        seen = set()
        for sheet in workbook.worksheets:
            rows = sheet.iter_rows(values_only=True)
            headers = next(rows, None)
            if not headers:
                continue
            matched = _mapping(headers, overrides)
            for row_number, cells in enumerate(rows, start=2):
                if not any(cell is not None for cell in cells):
                    continue
                counts["total"] += 1
                if counts["total"] > 2000:
                    raise HTTPException(413, "Workbook exceeds the 2,000-row import safety limit.")
                fields = {key: _value(cells[index] if index < len(cells) else None)
                          for key, index in matched.items()}
                code = (fields.get("supplier_code") or "").upper()
                name = fields.get("legal_name") or ""
                errors = []
                if not code: errors.append("missing_supplier_code")
                if not name: errors.append("missing_legal_name")
                if len(code) > 64: errors.append("supplier_code_too_long")
                if len(name) > 255: errors.append("legal_name_too_long")
                if any(isinstance(cell, str) and cell.startswith("=") for cell in cells):
                    errors.append("formula_requires_manual_review")
                if code:
                    if code in seen:
                        errors.append("duplicate_in_workbook")
                    seen.add(code)
                    existing = db.execute(text("""SELECT 1 FROM procurement_suppliers
                        WHERE amo_id=:amo AND upper(supplier_code)=:code LIMIT 1"""),
                        {"amo": tenant, "code": code}).scalar()
                    if existing:
                        errors.append("existing_supplier")
                if "duplicate_in_workbook" in errors or "existing_supplier" in errors:
                    counts["duplicates"] += 1
                state = "ERROR" if errors else "READY"
                counts["errors" if errors else "ready"] += 1
                db.execute(text("""INSERT INTO external_provider_import_rows
                    (id, amo_id, batch_id, sheet_name, row_number, raw_json,
                     normalized_json, diagnostics_json, status)
                    VALUES (:id, :amo, :batch, :sheet, :row, :raw, :norm, :errors, :state)"""),
                    {"id": str(uuid4()), "amo": tenant, "batch": batch_id,
                     "sheet": sheet.title[:128], "row": row_number,
                     "raw": json.dumps([_value(cell) for cell in cells]),
                     "norm": json.dumps(fields), "errors": json.dumps(errors), "state": state})
        db.commit()
        return {"batch_id": batch_id, "source_sha256": digest, "counts": counts, "status": "STAGED"}
    except Exception:
        db.rollback()
        raise
    finally:
        workbook.close()

@router.get("/external-provider-imports/{batch_id}")
def review(amo_code: str, batch_id: str, db: Session = Depends(get_db),
           user: accounts.User = Depends(get_current_active_user)):
    tenant = _tenant(db, amo_code, user)
    batch = db.execute(text("""SELECT * FROM external_provider_import_batches
        WHERE id=:batch AND amo_id=:amo"""), {"batch":batch_id, "amo":tenant}).mappings().first()
    if not batch:
        raise HTTPException(404, "Import batch not found.")
    rows = db.execute(text("""SELECT id, sheet_name, row_number, normalized_json,
            diagnostics_json, status, supplier_id FROM external_provider_import_rows
            WHERE batch_id=:batch AND amo_id=:amo ORDER BY sheet_name,row_number LIMIT 2000"""),
            {"batch":batch_id, "amo":tenant}).mappings().all()
    return {"batch":dict(batch), "rows":[dict(row) for row in rows]}

@router.post("/external-provider-imports/{batch_id}/confirm")
def confirm(amo_code: str, batch_id: str, db: Session = Depends(get_db),
            user: accounts.User = Depends(require_roles(*_EDIT))):
    tenant = _tenant(db, amo_code, user)
    batch = db.execute(text("""SELECT status FROM external_provider_import_batches
            WHERE id=:batch AND amo_id=:amo FOR UPDATE"""),
            {"batch":batch_id, "amo":tenant}).mappings().first()
    if not batch: raise HTTPException(404, "Import batch not found.")
    if batch["status"] != "STAGED":
        raise HTTPException(409, "This batch has already been processed.")
    rows = db.execute(text("""SELECT * FROM external_provider_import_rows
        WHERE amo_id=:amo AND batch_id=:batch ORDER BY sheet_name,row_number FOR UPDATE"""),
        {"amo":tenant,"batch":batch_id}).mappings().all()
    if not rows or any(row["status"] != "READY" for row in rows):
        raise HTTPException(409, "Batch has unresolved errors or no records.")
    created = []
    for row in rows:
        fields = row["normalized_json"]
        if isinstance(fields, str):
            fields = json.loads(fields)
        code = fields["supplier_code"].strip().upper()
        existing = db.execute(text("""SELECT 1 FROM procurement_suppliers
            WHERE amo_id=:amo AND upper(supplier_code)=:code"""),
            {"amo":tenant,"code":code}).scalar()
        if existing: raise HTTPException(409, "Concurrent duplicate supplier. Preview again.")
        supplier = models.ProcurementSupplier(
            amo_id=tenant, supplier_code=code, legal_name=fields["legal_name"].strip(),
            trading_name=fields.get("trading_name"), email=fields.get("email"),
            phone=fields.get("phone"), country=fields.get("country"),
            physical_address=fields.get("physical_address"),
            supplier_type="OTHER", status=models.SupplierLifecycleStatus.PROSPECTIVE,
            is_active=True, created_by_user_id=str(user.id),
        )
        db.add(supplier)
        db.flush()
        service._event(db, amo_id=tenant, entity_type="ProcurementSupplier",
                       entity_id=str(supplier.id), action="import_prospective",
                       actor_user_id=str(user.id),
                       detail={"batch_id":batch_id, "sheet":row["sheet_name"],
                               "row_number":row["row_number"]})
        db.execute(text("""UPDATE external_provider_import_rows
            SET status='CREATED', supplier_id=:supplier
            WHERE id=:row AND amo_id=:amo"""),
            {"supplier":supplier.id,"row":row["id"],"amo":tenant})
        created.append(supplier.id)
    db.execute(text("""UPDATE external_provider_import_batches SET
        status='COMMITTED', committed_at=now() WHERE id=:batch AND amo_id=:amo"""),
        {"batch":batch_id,"amo":tenant})
    db.commit()
    return {"batch_id":batch_id,"created_supplier_ids":created,
            "operational_eligibility_granted":False}
