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
from sqlalchemy.exc import IntegrityError
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
_EDIT = (accounts.AccountRole.PROCUREMENT_OFFICER, accounts.AccountRole.STORES_MANAGER,
         accounts.AccountRole.QUALITY_MANAGER)
_COLUMNS = {
    "supplier_code": ("supplier code", "vendor code", "vendor id", "supplier id", "code"),
    "legal_name": ("supplier name", "vendor name", "provider name", "company name", "name"),
    "trading_name": ("trading name",),
    "email": ("email", "email address"),
    "phone": ("phone", "telephone"),
    "country": ("country",),
    "physical_address": ("address", "physical address"),
    "source_status": ("approval status", "status", "quality status", "vendor status"),
}
_CONTRACT_COLUMNS = {
    "contract_number": ("contract number", "agreement number", "agreement ref", "reference number"),
    "supplier_code": ("vendor code", "supplier code", "provider code"),
    "supplier_name": ("vendor name", "supplier name", "contractor", "provider name"),
    "title": ("contract title", "agreement title", "description"),
    "scope_text": ("scope", "scope of work", "services"),
    "effective_on": ("effective date", "start date"),
    "expires_on": ("expiry date", "expiration date", "end date"),
    "source_status": ("status", "approval status", "contract status"),
    "controlled_document_id": ("dms document id", "controlled document id"),
    "controlled_document_revision": ("dms revision id", "controlled document revision"),
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

def _mapping(headers, overrides, columns):
    mapping = {}
    for field, aliases in columns.items():
        allowed = {_key(value) for value in (*aliases, overrides.get(field, ""))}
        for index, header in enumerate(headers):
            if _key(header) in allowed:
                mapping[field] = index
                break
    return mapping

@router.post("/external-provider-imports/preview", status_code=201)
async def preview(amo_code: str, file: UploadFile = File(...), mapping_json: str = Form("{}"),
                  import_kind: str = Form("SUPPLIERS"), source_sheet: str = Form(""),
                  header_row: int = Form(1),
                  db: Session = Depends(get_db),
                  user: accounts.User = Depends(require_roles(*_EDIT))):
    tenant = _tenant(db, amo_code, user)
    import_kind = import_kind.strip().upper()
    if import_kind not in ("SUPPLIERS", "CONTRACTS"):
        raise HTTPException(422, "Unknown spreadsheet import kind.")
    if header_row < 1 or header_row > 100:
        raise HTTPException(422, "Header row must be between 1 and 100.")
    columns = _COLUMNS if import_kind == "SUPPLIERS" else _CONTRACT_COLUMNS
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(415, "Only XLSX and XLSM files are supported.")
    try:
        overrides = json.loads(mapping_json)
        if not isinstance(overrides, dict) or any(
            key not in columns or not isinstance(value, str)
            for key, value in overrides.items()
        ):
            raise ValueError()
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Invalid source column mapping.") from exc
    mapping_digest = hashlib.sha256(json.dumps({"mapping":overrides,"sheet":source_sheet,"header_row":header_row},
                                               sort_keys=True).encode("utf-8")).hexdigest()
    data = await file.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise HTTPException(413, "Workbook exceeds 10 MB.")
    digest = hashlib.sha256(data).hexdigest()
    existing = db.execute(text("""SELECT id, status FROM external_provider_import_batches
        WHERE amo_id=:amo AND source_sha256=:digest AND import_kind=:kind
        AND mapping_digest=:mapping_digest"""),
        {"amo":tenant,"digest":digest,"kind":import_kind,
         "mapping_digest":mapping_digest}).mappings().first()
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
            (id, amo_id, filename, source_sha256, mapping_json, mapping_digest,
             import_kind, source_sheet, header_row, created_by_user_id)
            VALUES (:id, :amo, :filename, :digest, CAST(:mapping AS JSON), :mapping_digest,
                    :kind, :sheet, :header_row, :actor)"""),
            {"id": batch_id, "amo": tenant, "filename": filename[:255],
             "digest": digest, "mapping":json.dumps(overrides), "mapping_digest":mapping_digest,
             "kind":import_kind,
             "sheet":source_sheet[:128] or None, "header_row":header_row,
             "actor": str(user.id)})
        seen = set()
        seen_names = set()
        matched_sheet = False
        for sheet in workbook.worksheets:
            if source_sheet and sheet.title != source_sheet:
                continue
            matched_sheet = True
            rows = sheet.iter_rows(values_only=True)
            for _ in range(header_row - 1):
                next(rows, None)
            headers = next(rows, None)
            if not headers:
                continue
            matched = _mapping(headers, overrides, columns)
            for row_number, cells in enumerate(rows, start=header_row + 1):
                if not any(cell is not None for cell in cells):
                    continue
                counts["total"] += 1
                if counts["total"] > 2000:
                    raise HTTPException(413, "Workbook exceeds the 2,000-row import safety limit.")
                fields = {key: _value(cells[index] if index < len(cells) else None)
                          for key, index in matched.items()}
                errors = []
                limits = {"supplier_code":64,"legal_name":255,"trading_name":255,
                          "email":255,"phone":64,"country":64,"contract_number":128,
                          "supplier_name":255,"title":255,"controlled_document_id":64,
                          "controlled_document_revision":64}
                for column,maximum in limits.items():
                    if fields.get(column) and len(fields[column])>maximum:
                        errors.append(column + "_too_long")
                supplier_id = None
                if any(isinstance(cell, str) and cell.startswith("=") for cell in cells):
                    errors.append("formula_requires_manual_review")
                if import_kind == "SUPPLIERS":
                    code = (fields.get("supplier_code") or "").strip().upper()
                    name = fields.get("legal_name") or ""
                    if not code: errors.append("missing_supplier_code")
                    if not name: errors.append("missing_legal_name")
                    if len(code) > 64: errors.append("supplier_code_too_long")
                    if len(name) > 255: errors.append("legal_name_too_long")
                    if name:
                        normalized_name = " ".join(name.upper().split())
                        if normalized_name in seen_names:
                            errors.append("duplicate_legal_name_in_workbook")
                        seen_names.add(normalized_name)
                        existing_name = db.execute(text("""SELECT id FROM procurement_suppliers
                            WHERE amo_id=:amo AND lower(trim(legal_name))=lower(trim(:name)) LIMIT 1"""),
                            {"amo":tenant,"name":name}).scalar()
                        if existing_name: errors.append("existing_legal_name_reconcile_first")
                    if code:
                        if code in seen: errors.append("duplicate_in_workbook")
                        seen.add(code)
                        existing = db.execute(text("""SELECT id FROM procurement_suppliers
                            WHERE amo_id=:amo AND upper(supplier_code)=:code LIMIT 1"""),
                            {"amo":tenant,"code":code}).scalar()
                        if existing: errors.append("existing_supplier")
                else:
                    contract_no = (fields.get("contract_number") or "").strip()
                    key = contract_no.upper()
                    if not contract_no: errors.append("missing_contract_number")
                    if len(contract_no) > 128: errors.append("contract_number_too_long")
                    if not fields.get("title"): errors.append("missing_contract_title")
                    if not fields.get("scope_text"): errors.append("missing_scope_of_work")
                    if bool(fields.get("controlled_document_id")) != bool(fields.get("controlled_document_revision")):
                        errors.append("document_and_exact_revision_required_together")
                    if key:
                        if key in seen: errors.append("duplicate_in_workbook")
                        seen.add(key)
                        existing_contract = db.execute(text("""SELECT 1
                            FROM quality_external_provider_contracts
                            WHERE amo_id=:amo AND upper(contract_number)=:number LIMIT 1"""),
                            {"amo":tenant,"number":key}).scalar()
                        if existing_contract: errors.append("existing_contract")
                    code = (fields.get("supplier_code") or "").strip().upper()
                    name = (fields.get("supplier_name") or "").strip()
                    if code:
                        matches = db.execute(text("""SELECT id FROM procurement_suppliers
                            WHERE amo_id=:amo AND upper(supplier_code)=:code LIMIT 2"""),
                            {"amo":tenant,"code":code}).scalars().all()
                    elif name:
                        matches = db.execute(text("""SELECT id FROM procurement_suppliers
                            WHERE amo_id=:amo AND lower(legal_name)=lower(:name) LIMIT 2"""),
                            {"amo":tenant,"name":name}).scalars().all()
                    else:
                        matches = []
                    if len(matches) != 1: errors.append("supplier_match_missing_or_ambiguous")
                    else: supplier_id = matches[0]
                    for key in ("effective_on","expires_on"):
                        value = fields.get(key)
                        if value:
                            try:
                                fields[key] = date.fromisoformat(value[:10]).isoformat()
                            except (TypeError, ValueError):
                                errors.append("invalid_" + key + "_use_iso_date")
                    if fields.get("effective_on") and fields.get("expires_on"):
                        try:
                            if fields["expires_on"] < fields["effective_on"]:
                                errors.append("expiry_precedes_effective_date")
                        except TypeError:
                            pass
                if any(item in errors for item in ("duplicate_in_workbook","existing_supplier",
                       "existing_contract","duplicate_legal_name_in_workbook",
                       "existing_legal_name_reconcile_first")):
                    counts["duplicates"] += 1
                state = "ERROR" if errors else "READY"
                counts["errors" if errors else "ready"] += 1
                db.execute(text("""INSERT INTO external_provider_import_rows
                    (id, amo_id, batch_id, sheet_name, row_number, raw_json,
                     normalized_json, diagnostics_json, status, supplier_id)
                    VALUES (:id, :amo, :batch, :sheet, :row, CAST(:raw AS JSON),
                            CAST(:norm AS JSON),CAST(:errors AS JSON), :state, :supplier)"""),
                    {"id":str(uuid4()),"amo":tenant,"batch":batch_id,"sheet":sheet.title[:128],
                     "row":row_number,"raw":json.dumps([_value(cell) for cell in cells]),
                     "norm":json.dumps(fields),"errors":json.dumps(errors),
                     "state":state,"supplier":supplier_id})
        if not matched_sheet:
            raise HTTPException(422, "Selected worksheet not found.")
        service._event(db,amo_id=tenant,entity_type="ExternalProviderImport",
                       entity_id=batch_id,action="stage_preview",actor_user_id=str(user.id),
                       detail={"import_kind":import_kind,"source_sha256":digest,
                               "source_sheet":source_sheet,"counts":counts})
        db.commit()
        return {"batch_id":batch_id, "source_sha256":digest, "import_kind":import_kind,
                "counts":counts,"status":"STAGED"}
    except IntegrityError as exc:
        db.rollback()
        existing = db.execute(text("""SELECT id,status FROM external_provider_import_batches
            WHERE amo_id=:amo AND source_sha256=:digest AND import_kind=:kind
            AND mapping_digest=:mapping_digest"""),
            {"amo":tenant,"digest":digest,"kind":import_kind,
             "mapping_digest":mapping_digest}).mappings().first()
        if existing:
            return {"batch_id":existing["id"],"source_sha256":digest,
                    "import_kind":import_kind,"status":existing["status"],"already_uploaded":True}
        raise HTTPException(409,"Workbook has duplicate or incompatible records.") from exc
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
    batch = db.execute(text("""SELECT status,import_kind,source_sha256 FROM external_provider_import_batches
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
    if batch["import_kind"] == "CONTRACTS" and user.role != accounts.AccountRole.QUALITY_MANAGER:
        raise HTTPException(403, "Only the Quality Manager can confirm governed contract drafts.")
    created = []
    for row in rows:
        fields = row["normalized_json"]
        if isinstance(fields, str):
            fields = json.loads(fields)
        if batch["import_kind"] == "CONTRACTS":
            supplier_id = row["supplier_id"]
            if not supplier_id:
                raise HTTPException(409, "Unmatched contract provider.")
            exists = db.execute(text("""SELECT 1 FROM quality_external_provider_contracts
                WHERE amo_id=:amo AND upper(contract_number)=upper(:number)"""),
                {"amo":tenant,"number":fields["contract_number"]}).scalar()
            if exists: raise HTTPException(409, "Contract number now exists. Reconcile first.")
            contract_id = str(uuid4())
            db.execute(text("""INSERT INTO quality_external_provider_contracts
                (id,amo_id,supplier_id,contract_number,title,status,scope_text,
                 effective_on,expires_on,controlled_document_id,controlled_document_revision,
                 created_by_user_id,updated_by_user_id)
                 VALUES (:id,:amo,:supplier,:number,:title,'DRAFT',:scope,
                         :effective,:expires,:document,:revision,:actor,:actor)"""),
                 {"id":contract_id,"amo":tenant,"supplier":supplier_id,
                  "number":fields["contract_number"],"title":fields["title"],
                  "scope":fields["scope_text"],"effective":fields.get("effective_on"),
                  "expires":fields.get("expires_on"),"document":fields.get("controlled_document_id"),
                  "revision":fields.get("controlled_document_revision"),"actor":str(user.id)})
            db.execute(text("""UPDATE external_provider_import_rows
                SET status='CREATED',contract_id=:contract
                WHERE id=:row AND amo_id=:amo"""),
                {"contract":contract_id,"row":row["id"],"amo":tenant})
            record_id = contract_id
            action = "import_contract_draft"
        else:
            code = fields["supplier_code"].strip().upper()
            exists = db.execute(text("""SELECT 1 FROM procurement_suppliers
                WHERE amo_id=:amo AND upper(supplier_code)=:code"""),
                {"amo":tenant,"code":code}).scalar()
            if exists: raise HTTPException(409, "Supplier was added after preview; stage again.")
            supplier = models.ProcurementSupplier(
                amo_id=tenant,supplier_code=code,legal_name=fields["legal_name"].strip(),
                trading_name=fields.get("trading_name"),email=fields.get("email"),
                phone=fields.get("phone"),country=fields.get("country"),
                physical_address=fields.get("physical_address"),supplier_type="OTHER",
                status=models.SupplierLifecycleStatus.PROSPECTIVE,is_active=False,
                external_import_pending_activation=True,created_by_user_id=str(user.id),
            )
            db.add(supplier)
            try:
                db.flush()
            except IntegrityError as exc:
                db.rollback()
                raise HTTPException(409,"Concurrent supplier insertion; re-stage the file.") from exc
            supplier_id = supplier.id
            record_id = str(supplier_id)
            action = "import_prospective"
            db.execute(text("""INSERT INTO external_provider_source_links
                (id,amo_id,supplier_id,source_system,source_identifier,source_row,source_digest,imported_at)
                VALUES (:id,:amo,:supplier,'TRACKER_IMPORT',:source,:row,
                        :digest,NOW())"""),
                {"id":str(uuid4()),"amo":tenant,"supplier":supplier_id,
                 "source":batch_id+":"+row["sheet_name"]+":"+str(row["row_number"]),
                 "row":row["row_number"],"digest":batch["source_sha256"]})
            db.execute(text("""UPDATE external_provider_import_rows
                SET status='CREATED',supplier_id=:supplier
                WHERE id=:row AND amo_id=:amo"""),
                {"supplier":supplier_id,"row":row["id"],"amo":tenant})
        service._event(db,amo_id=tenant,entity_type="ExternalProviderImport",
                       entity_id=record_id,action=action,actor_user_id=str(user.id),
                       detail={"batch_id":batch_id,"sheet":row["sheet_name"],
                               "row_number":row["row_number"]})
        db.execute(text("""INSERT INTO external_provider_change_events
            (id,amo_id,supplier_id,event_type,actor_user_id,source_system,
             source_identifier,after_json)
            VALUES (:id,:amo,:supplier,:action,:actor,'TRACKER_IMPORT',:source,
                    CAST(:payload AS JSON))"""),
            {"id":str(uuid4()),"amo":tenant,"supplier":supplier_id,"action":action,
             "actor":str(user.id),"source":batch_id+":"+str(row["row_number"]),
             "payload":json.dumps({"fields":fields,"sheet":row["sheet_name"]})})
        created.append(record_id)
    db.execute(text("""UPDATE external_provider_import_batches SET
        status='COMMITTED', committed_at=now() WHERE id=:batch AND amo_id=:amo"""),
        {"batch":batch_id,"amo":tenant})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409,"Import reconciliation conflict; refresh before retrying.") from exc
    return {"batch_id":batch_id,"created_record_ids":created,
            "created_supplier_ids":created if batch["import_kind"] == "SUPPLIERS" else [],
            "import_kind":batch["import_kind"],"operational_eligibility_granted":False}


@router.post("/external-provider-imports/{batch_id}/supersede")
def supersede(amo_code: str, batch_id: str, reason: str = Form(...),
              db: Session = Depends(get_db),
              user: accounts.User = Depends(require_roles(*_EDIT))):
    if len(reason.strip()) < 8:
        raise HTTPException(422, "Document the replacement reason.")
    tenant = _tenant(db, amo_code, user)
    batch = db.execute(text("""SELECT id,status FROM external_provider_import_batches
        WHERE amo_id=:amo AND id=:batch FOR UPDATE"""),
        {"amo":tenant,"batch":batch_id}).mappings().first()
    if not batch: raise HTTPException(404, "Import batch was not found.")
    if batch["status"] != "STAGED":
        raise HTTPException(409, "Only unconfirmed batches may be superseded.")
    db.execute(text("""UPDATE external_provider_import_batches
        SET status='SUPERSEDED' WHERE amo_id=:amo AND id=:batch"""),
        {"amo":tenant,"batch":batch_id})
    service._event(db, amo_id=tenant,entity_type="ExternalProviderImport",
                   entity_id=batch_id,action="supersede_preview",
                   actor_user_id=str(user.id),detail={"reason":reason})
    db.commit()
    return {"batch_id":batch_id,"status":"SUPERSEDED"}

@router.post("/external-provider-imports/{batch_id}/rollback")
def rollback_import(amo_code: str, batch_id: str, reason: str = Form(...),
                    db: Session = Depends(get_db),
                    user: accounts.User = Depends(require_roles(*_EDIT))):
    if len(reason.strip()) < 8:
        raise HTTPException(422,"A documented rollback reason is required.")
    tenant = _tenant(db,amo_code,user)
    batch = db.execute(text("""SELECT * FROM external_provider_import_batches
        WHERE amo_id=:amo AND id=:batch FOR UPDATE"""),
        {"amo":tenant,"batch":batch_id}).mappings().first()
    if not batch: raise HTTPException(404,"Import batch not found.")
    if batch["status"] != "COMMITTED":
        raise HTTPException(409,"Only committed batches may be rolled back.")
    if batch["import_kind"] == "CONTRACTS" and user.role != accounts.AccountRole.QUALITY_MANAGER:
        raise HTTPException(403,"Quality Manager authority is required for contracts.")
    rows = db.execute(text("""SELECT * FROM external_provider_import_rows
        WHERE amo_id=:amo AND batch_id=:batch ORDER BY row_number FOR UPDATE"""),
        {"amo":tenant,"batch":batch_id}).mappings().all()
    for row in rows:
        if row["status"] != "CREATED":
            raise HTTPException(409,"Import has been modified; individual review required.")
        if batch["import_kind"] == "CONTRACTS":
            contract = db.execute(text("""SELECT status,version FROM quality_external_provider_contracts
                WHERE amo_id=:amo AND supplier_id=:supplier AND id=:contract FOR UPDATE"""),
                {"amo":tenant,"supplier":row["supplier_id"],
                 "contract":row["contract_id"]}).mappings().first()
            if not contract or contract["status"] != "DRAFT" or contract["version"] != 1:
                raise HTTPException(409,"Contract has progressed beyond unmodified draft.")
        else:
            supplier = db.execute(text("""SELECT status,approved_at FROM procurement_suppliers
                WHERE amo_id=:amo AND id=:supplier FOR UPDATE"""),
                {"amo":tenant,"supplier":row["supplier_id"]}).mappings().first()
            if not supplier or str(supplier["status"]) not in ("PROSPECTIVE",) or supplier["approved_at"]:
                raise HTTPException(409,"Imported supplier has progressed in Quality governance.")
            # Never archive suppliers that have become referenced in live work.
            linked = db.execute(text("""SELECT
                 EXISTS(SELECT 1 FROM procurement_purchase_orders
                        WHERE amo_id=:amo AND supplier_id=:supplier)
                 OR EXISTS(SELECT 1 FROM procurement_quotes
                        WHERE amo_id=:amo AND supplier_id=:supplier)
                 OR EXISTS(SELECT 1 FROM procurement_supplier_evaluations
                        WHERE amo_id=:amo AND supplier_id=:supplier)
                 OR EXISTS(SELECT 1 FROM quality_external_provider_profiles
                        WHERE amo_id=:amo AND supplier_id=:supplier)
                 OR EXISTS(SELECT 1 FROM quality_external_provider_contracts
                        WHERE amo_id=:amo AND supplier_id=:supplier)
                 OR EXISTS(SELECT 1 FROM procurement_supplier_approval_scopes
                        WHERE amo_id=:amo AND supplier_id=:supplier)"""),
                {"amo":tenant,"supplier":row["supplier_id"]}).scalar()
            if linked:
                raise HTTPException(409,"Supplier is already used or governed; rollback forbidden.")
    for row in rows:
        if batch["import_kind"] == "CONTRACTS":
            db.execute(text("""UPDATE quality_external_provider_contracts
                SET status='SUPERSEDED', version=version+1,
                    transition_reason=:reason,updated_at=NOW()
                WHERE amo_id=:amo AND id=:contract"""),
                {"amo":tenant,"contract":row["contract_id"],"reason":reason})
        else:
            db.execute(text("""UPDATE procurement_suppliers
                SET status='ARCHIVED',is_active=false,updated_at=NOW()
                WHERE amo_id=:amo AND id=:supplier"""),
                {"amo":tenant,"supplier":row["supplier_id"]})
        db.execute(text("""UPDATE external_provider_import_rows SET status='ROLLED_BACK'
            WHERE amo_id=:amo AND id=:row"""),{"amo":tenant,"row":row["id"]})
    db.execute(text("""UPDATE external_provider_import_batches SET status='ROLLED_BACK'
        WHERE amo_id=:amo AND id=:batch"""),{"amo":tenant,"batch":batch_id})
    service._event(db,amo_id=tenant,entity_type="ExternalProviderImport",entity_id=batch_id,
                   action="controlled_rollback",actor_user_id=str(user.id),
                   detail={"reason":reason,"record_count":len(rows),
                           "import_kind":batch["import_kind"]})
    db.commit()
    return {"batch_id":batch_id,"status":"ROLLED_BACK",
            "records_reconciled":len(rows)}
