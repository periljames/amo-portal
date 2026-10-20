"""Phase 5 provider-controlled document intake and DMS/QMS links.

No provider receives an internal DMS or QMS token. Original files remain
byte-identical in the existing shared storage; review creates only references
in the canonical QMS evidence register, never an independent approval.
"""
from __future__ import annotations

import codecs
import hashlib
import json
import os
import re
import shutil
import socket
import struct
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session

from amodb import storage
from amodb.database import get_db
from amodb.security import get_current_active_user
from amodb.apps.accounts import models as accounts
from amodb.apps.procurement import external_auth_core as auth
from amodb.apps.procurement import external_partner_router as partner
from amodb.apps.procurement import service as procurement_service

partner_documents_router = APIRouter(
    prefix="/api/external-provider/partner/{tenant_slug}/documents",
    tags=["Provider controlled documents"],
)
staff_documents_router = APIRouter(
    prefix="/api/maintenance/{amo_code}/quality/external-accounts/documents",
    tags=["Quality provider document intake"],
)
MAX_FILE_BYTES = 20 * 1024 * 1024
EXT_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".txt": "text/plain",
}
KINDS = frozenset({"ALL","SUPPLIER","CONTRACTOR","SUBCONTRACTOR","SERVICE_PROVIDER",
    "CONSULTANT","LABORATORY","CALIBRATION_PROVIDER","OTHER"})
CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,47}$")


def _one(db, sql, **kw):
    r = db.execute(text(sql),kw).mappings().first()
    return dict(r) if r else None


def _all(db, sql, **kw):
    return [dict(r) for r in db.execute(text(sql),kw).mappings()]


def _event(db, amo, submission, action, *, identity=None, actor=None, details=None):
    db.execute(text("""INSERT INTO external_provider_document_events
      (id,amo_id,submission_id,actor_identity_id,actor_user_id,action,details_json)
      VALUES(:id,:amo,:submission,:identity,:actor,:action,CAST(:details AS JSON))"""),
      {"id":str(uuid4()),"amo":amo,"submission":submission,"identity":identity,
       "actor":actor,"action":action,"details":json.dumps(details or {})})


def _requirement(db, amo, supplier, requirement_id):
    requirement = _one(db, """SELECT r.*, p.provider_kind AS resolved_provider_kind FROM
      external_provider_document_requirements r
      LEFT JOIN quality_external_provider_profiles p
        ON p.amo_id=r.amo_id AND p.supplier_id=:supplier
      WHERE r.amo_id=:amo AND r.id=:id AND r.enabled=true
        AND (r.provider_kind='ALL' OR r.provider_kind=COALESCE(p.provider_kind,'SUPPLIER'))""",
      amo=amo,supplier=supplier,id=requirement_id)
    if not requirement:
        raise HTTPException(404,"The document requirement is not assigned to this provider category")
    return requirement


def _published_revision(db, amo, manual_id, revision_id, *, current=True):
    condition="AND m.current_published_rev_id=r.id" if current else ""
    row=_one(db,"""SELECT r.id,r.rev_number,r.source_filename,r.source_storage_path,
        r.source_mime_type,r.source_sha256,r.published_at
      FROM manuals m JOIN manual_tenants t ON t.id=m.tenant_id
      JOIN manual_revisions r ON r.manual_id=m.id
      WHERE t.amo_id=:amo AND m.id=:manual AND r.id=:revision
        AND r.status_enum='PUBLISHED' AND r.published_at IS NOT NULL """ + condition,
      amo=amo,manual=manual_id,revision=revision_id)
    if not row:
        raise HTTPException(409,"Controlled source must resolve to an exact published DMS revision in this tenant")
    return row


def _staff_published_revision(db, amo, manual_id, revision_id, user):
    # Quality staff may review provider evidence, but cannot bypass a
    # restricted DMS document profile or acquire Document Control authority.
    from amodb.apps.doc_control import domain_models as dms_models
    from amodb.apps.doc_control.workspace_service import require_manual_access
    profile=db.query(dms_models.DocumentControlProfile).filter(
        dms_models.DocumentControlProfile.tenant_id==amo,
        dms_models.DocumentControlProfile.manual_id==manual_id).first()
    require_manual_access(user,profile)
    return _published_revision(db,amo,manual_id,revision_id)


def _scan_clamd(path: str):
    """Bounded streaming ClamAV scan. Fail closed if scanner is not configured.

    CLAMD uses INSTREAM; this does not execute user data or transform originals.
    """
    host = os.getenv("PROVIDER_DOCUMENT_CLAMD_HOST","").strip()
    if not host:
        raise HTTPException(503,"Provider intake requires a configured antivirus scanner")
    try:
        port=int(os.getenv("PROVIDER_DOCUMENT_CLAMD_PORT","3310"))
        if not 1<=port<=65535:raise ValueError("Port out of range")
    except ValueError as exc:
        raise HTTPException(503,"Provider intake malware scanner configuration is invalid") from exc
    try:
        timeout=int(os.getenv("PROVIDER_DOCUMENT_CLAMD_SCAN_TIMEOUT_SECONDS","240"))
        if not 30<=timeout<=900:
            raise ValueError("scan timeout outside 30–900 seconds")
    except ValueError as exc:
        raise HTTPException(503,"Document scanner timeout configuration invalid") from exc
    try:
        with socket.create_connection((host,port),timeout=8) as sock:
            sock.settimeout(timeout)
            sock.sendall(b"zINSTREAM\x00")
            with open(path,"rb") as file:
                while chunk:=file.read(65536):
                    sock.sendall(struct.pack("!I",len(chunk))+chunk)
            sock.sendall(struct.pack("!I",0))
            result=b""
            while len(result)<512 and not result.endswith(b"\x00"):
                chunk=sock.recv(512-len(result))
                if not chunk:break
                result+=chunk
    except (OSError,ValueError) as exc:
        raise HTTPException(503,"Document malware scanner is unavailable; file not accepted") from exc
    if not result.rstrip(b"\x00").endswith(b" OK"):
        raise HTTPException(415,"File did not pass the required malware scan")


def _validate_file(path: Path, original: str, declared: str):
    extension=Path(original).suffix.lower()
    if extension not in EXT_MIME or declared.split(";",1)[0].strip().lower()!=EXT_MIME[extension]:
        raise HTTPException(415,"File format and MIME type must match an allowed format")
    with path.open("rb") as f:
        first=f.read(32)
    if extension==".pdf":
        valid=first.startswith(b"%PDF-")
    elif extension==".png":
        valid=first.startswith(b"\x89PNG\r\n\x1a\n")
    elif extension in {".jpg",".jpeg"}:
        valid=first.startswith(b"\xff\xd8\xff")
    elif extension==".docx":
        valid=first.startswith(b"PK\x03\x04")
        if valid:
            try:
                with zipfile.ZipFile(path) as archive:
                    names=set(archive.namelist())
                    valid={"[Content_Types].xml","word/document.xml"}.issubset(names)
                    valid=valid and not any(n.lower().endswith(("vbaproject.bin",".exe",".js")) for n in names)
                    valid=valid and len(names)<=3000 and sum(x.file_size for x in archive.infolist())<=100*1024*1024
            except (zipfile.BadZipFile,RuntimeError):
                valid=False
    else:
        try:
            decoder=codecs.getincrementaldecoder("utf-8-sig")()
            valid=True
            with path.open("rb") as stream:
                while chunk:=stream.read(1024*1024):
                    if b"\x00" in chunk:
                        valid=False
                        break
                    decoder.decode(chunk,final=False)
                decoder.decode(b"",final=True)
        except UnicodeDecodeError:
            valid=False
    if not valid:
        raise HTTPException(415,"The file content does not match a safe document of its declared type")


def _governed_procurement_upload(db,user,kind,item):
    """Recheck supplier work eligibility before accepting commercial source files.

    Existing provider/qualification evidence is unaffected. A disabled or
    restricted supplier cannot stage a new invoice, quotation or shipment.
    Restore the member RLS marker after the internal QMS lookup.
    """
    if kind=="CONTRACTED_WORK":
        partner._cap(user,"document.submit")
        ctx=partner._context(user)
        work=_one(db,"""SELECT id,status FROM external_contracted_work
             WHERE amo_id=:amo AND supplier_id=:supplier AND provider_id=:provider AND id=:id""",
             **ctx,id=item)
        if not work or work["status"] not in ("AUTHORIZED","DISPATCHED","PROVIDER_ACCEPTED",
            "IN_PROGRESS","ADDITIONAL_WORK_REQUESTED","WORK_COMPLETED",
            "RELEASE_SUBMITTED","RETURNED","INSPECTION","REWORK_REQUIRED","ON_HOLD"):
            raise HTTPException(409,"Contracted work is not authorized for evidence intake")
        return
    if kind not in {"RFQ","PO","SHIPMENT"}:
        return
    partner._cap(user,"procurement.attach")
    from .supplier_quality_control import assert_supplier_usage_allowed
    ctx=partner._context(user)
    if kind=="RFQ":
        category_sql="""SELECT CASE WHEN l.part_number IS NULL THEN 'SERVICE' ELSE 'PART' END
          FROM procurement_requisition_lines l JOIN procurement_rfqs r
            ON r.requisition_id=l.requisition_id
          JOIN procurement_rfq_suppliers i ON i.rfq_id=r.id
          WHERE r.amo_id=:amo AND i.supplier_id=:supplier AND CAST(r.id AS TEXT)=:id"""
    else:
        category_sql="""SELECT CASE WHEN l.part_number IS NULL THEN 'SERVICE' ELSE 'PART' END
          FROM procurement_purchase_order_lines l JOIN procurement_purchase_orders p
            ON p.id=l.purchase_order_id
          WHERE p.amo_id=:amo AND p.supplier_id=:supplier AND CAST(p.id AS TEXT)=:id"""
        if kind=="SHIPMENT":
            parent=_one(db,"""SELECT po_id FROM external_procurement_shipments
                 WHERE amo_id=:amo AND supplier_id=:supplier AND id=:id""",
                 amo=ctx["amo"],supplier=ctx["supplier"],id=item)
            if not parent:
                raise HTTPException(404,"Shipment no longer belongs to provider")
            item=str(parent["po_id"])
    categories=set(db.execute(text(category_sql),
        {"amo":ctx["amo"],"supplier":ctx["supplier"],"id":item}).scalars().all())
    if not categories:raise HTTPException(409,"No eligible issued transaction lines")
    try:
        assert_supplier_usage_allowed(db,amo_id=ctx["amo"],supplier_id=ctx["supplier"],
                                      categories=categories,allow_controlled_override=False)
    finally:
        if db.get_bind().dialect.name=="postgresql":
            db.execute(text("SELECT set_config('app.external_provider_id',:provider,true)"),
                       {"provider":ctx["provider"]})


def _staff(db, amo_code, user, manage=False):
    role=str(getattr(user.role,"value",user.role))
    accepted={"QUALITY_MANAGER"} if manage else {"QUALITY_MANAGER","QUALITY_OFFICER","DOCUMENT_CONTROL_OFFICER"}
    if role not in accepted:
        raise HTTPException(403,"Appointed Quality or Document Control authority required")
    amo=procurement_service.resolve_tenant_amo_id(db,amo_code=amo_code,current_user=user)
    auth.context(db,amo,str(user.id))
    if db.get_bind().dialect.name=="postgresql":
        db.execute(text("SELECT set_config('app.external_provider_id','__INTERNAL_QUALITY_REVIEW__',true)"))
    return amo


class RequirementWrite(BaseModel):
    provider_kind: str = Field(max_length=32)
    code: str = Field(max_length=48)
    title: str = Field(min_length=2,max_length=255)
    description: str = Field(default="",max_length=4000)
    mandatory: bool = False
    acknowledgement_required: bool = False
    expiry_required: bool = False
    reminder_days: int = Field(default=0,ge=0,le=365)
    form_manual_id: str | None = Field(default=None,max_length=36)
    form_revision_id: str | None = Field(default=None,max_length=36)
    retention_policy_ref: str | None = Field(default=None,max_length=128)
    enabled: bool = True
    expected_version: int | None = Field(default=None,ge=1)


@staff_documents_router.get("/permissions")
def document_permissions(amo_code:str,db:Session=Depends(get_db),
                         user=Depends(get_current_active_user)):
    _staff(db,amo_code,user)
    from amodb.apps.doc_control.workspace_service import is_control_user
    role=str(getattr(user.role,"value",user.role))
    return {"quality_manager":role=="QUALITY_MANAGER",
            "quality_reviewer":role in {"QUALITY_MANAGER","QUALITY_OFFICER"},
            "document_controller":is_control_user(user)}


@staff_documents_router.get("/requirements")
def staff_requirements(amo_code:str,db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    return {"items":_all(db,"""SELECT * FROM external_provider_document_requirements
        WHERE amo_id=:amo ORDER BY provider_kind,code""",amo=amo)}


@staff_documents_router.put("/requirements/{code}")
def save_requirement(amo_code:str,code:str,payload:RequirementWrite,
                     db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user,True)
    key=code.upper().strip()
    kind=payload.provider_kind.upper().strip()
    if not CODE.fullmatch(key) or payload.code.upper()!=key or kind not in KINDS:
        raise HTTPException(422,"Invalid requirement category/code")
    if bool(payload.form_manual_id)!=bool(payload.form_revision_id):
        raise HTTPException(422,"Form manual and exact revision must be supplied together")
    if payload.acknowledgement_required and not payload.form_revision_id:
        raise HTTPException(422,"Acknowledgement requires a published form revision")
    if payload.form_manual_id:
        _staff_published_revision(db,amo,payload.form_manual_id,payload.form_revision_id,user)
    existing=_one(db,"""SELECT id,version FROM external_provider_document_requirements
        WHERE amo_id=:amo AND provider_kind=:kind AND code=:code FOR UPDATE""",
        amo=amo,kind=kind,code=key)
    if existing and payload.expected_version!=existing["version"]:
        raise HTTPException(409,"Requirement was changed; reload its current version")
    if not existing and payload.expected_version is not None:
        raise HTTPException(409,"Requirement does not exist for the supplied revision")
    id=existing["id"] if existing else str(uuid4())
    db.execute(text("""INSERT INTO external_provider_document_requirements
        (id,amo_id,provider_kind,code,title,description,mandatory,acknowledgement_required,expiry_required,
         form_manual_id,form_revision_id,retention_policy_ref,enabled,reminder_days,created_by_user_id)
        VALUES(:id,:amo,:kind,:code,:title,:description,:mandatory,:ack,:expiry,
          :manual,:revision,:retention,:enabled,:reminder,:actor)
        ON CONFLICT (amo_id,provider_kind,code) DO UPDATE SET
          title=EXCLUDED.title,description=EXCLUDED.description,
          mandatory=EXCLUDED.mandatory,acknowledgement_required=EXCLUDED.acknowledgement_required,
           expiry_required=EXCLUDED.expiry_required,
          form_manual_id=EXCLUDED.form_manual_id,
          form_revision_id=EXCLUDED.form_revision_id,
          retention_policy_ref=EXCLUDED.retention_policy_ref,
          reminder_days=EXCLUDED.reminder_days,
          enabled=EXCLUDED.enabled,version=external_provider_document_requirements.version+1,
          updated_at=NOW()"""),{"id":id,"amo":amo,"kind":kind,"code":key,"title":payload.title,
          "description":payload.description,"mandatory":payload.mandatory,"ack":payload.acknowledgement_required,"expiry":payload.expiry_required,
          "manual":payload.form_manual_id,"revision":payload.form_revision_id,
          "retention":payload.retention_policy_ref,"enabled":payload.enabled,
          "reminder":payload.reminder_days,"actor":str(user.id)})
    auth.event(db,amo=amo,identity=None,grant=None,actor_user=str(user.id),
       action="EXTERNAL_DOCUMENT_POLICY_UPDATED",
       details={"requirement_id":id,"category":kind,"code":key,"version":(existing["version"]+1 if existing else 1)})
    db.commit()
    return {"id":id,"code":key,"version":(existing["version"]+1 if existing else 1)}


@partner_documents_router.get("/requirements")
def my_requirements(tenant_slug:str,request:Request,db:Session=Depends(get_db)):
    user=partner._ctx(db,request,tenant_slug,cap="document.read")
    ctx=partner._context(user)
    rows=_all(db,"""SELECT r.id,r.code,r.title,r.description,r.mandatory,
        r.expiry_required,r.acknowledgement_required,r.reminder_days,r.form_manual_id,r.form_revision_id,r.version,
        EXISTS(SELECT 1 FROM external_provider_form_acknowledgements a
          WHERE a.amo_id=r.amo_id AND a.tenant_provider_id=:provider
          AND a.identity_id=:person AND a.requirement_id=r.id
          AND a.form_revision_id=r.form_revision_id) AS acknowledged_by_me
        FROM external_provider_document_requirements r
        LEFT JOIN quality_external_provider_profiles p
          ON p.amo_id=r.amo_id AND p.supplier_id=:supplier
        WHERE r.amo_id=:amo AND r.enabled=true
          AND (r.provider_kind='ALL' OR r.provider_kind=COALESCE(p.provider_kind,'SUPPLIER'))
        ORDER BY r.mandatory DESC,r.code""",amo=ctx["amo"],supplier=ctx["supplier"],
        provider=ctx["provider"],person=ctx["person"])
    for row in rows:
        # Form download is still checked against member-specific document grants.
        row["form_available"]=bool(row["form_manual_id"] and
            str(row["form_manual_id"]) in partner._allowed(user,"documents"))
    return {"items":rows}


@partner_documents_router.get("/requirements/{requirement_id}/form")
def download_form(tenant_slug:str,requirement_id:str,request:Request,db:Session=Depends(get_db)):
    user=partner._ctx(db,request,tenant_slug,cap="document.read")
    ctx=partner._context(user)
    requirement=_requirement(db,ctx["amo"],ctx["supplier"],requirement_id)
    if not requirement["form_manual_id"]:
        raise HTTPException(404,"No controlled form assigned")
    partner._require_object(user,"documents",str(requirement["form_manual_id"]))
    revision=_published_revision(db,ctx["amo"],requirement["form_manual_id"],
        requirement["form_revision_id"])
    if not revision["source_storage_path"]:
        raise HTTPException(409,"Published controlled form has no original source")
    file=storage.materialize(revision["source_storage_path"],
        expected_sha256=revision["source_sha256"])
    auth.event(db,amo=ctx["amo"],identity=ctx["person"],grant=user["grant_id"],
        action="EXTERNAL_CONTROLLED_FORM_DOWNLOAD",actor_identity=ctx["person"],
        details={"requirement":requirement_id,"revision":revision["id"]})
    db.commit()
    return FileResponse(file,filename=Path(revision["source_filename"] or "controlled-form").name,
        media_type=revision["source_mime_type"] or "application/octet-stream",
        headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})


# Object-backed resumable intake. Parts are isolated to a single member/provider,
# retained until final checksum and ClamAV verification, then purged.
PART_BYTES=8*1024*1024
MAX_RESUMABLE_BYTES=512*1024*1024


class UploadStart(BaseModel):
    filename: str = Field(min_length=5,max_length=190)
    content_type: str = Field(min_length=3,max_length=128)
    size_bytes: int = Field(ge=1,le=MAX_RESUMABLE_BYTES)
    sha256: str | None = Field(default=None,pattern=r"^[a-f0-9]{64}$")
    requirement_id: str = Field(min_length=8,max_length=36)
    related_kind: Literal["PROVIDER","CONTRACT","ASSIGNMENT","RFQ","PO","SHIPMENT","CONTRACTED_WORK"] = "PROVIDER"
    related_id: str | None = None
    supersedes_submission_id: str | None = None
    valid_until: date | None = None
    retry_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{12,64}$")


def _upload_session(db,ctx,session_id,*,lock=False):
    suffix=" FOR UPDATE" if lock and db.get_bind().dialect.name=="postgresql" else ""
    session=_one(db,"""SELECT * FROM external_provider_upload_sessions
      WHERE amo_id=:amo AND tenant_provider_id=:provider
        AND identity_id=:person AND id=:id"""+suffix,
        **ctx,id=session_id)
    if not session:
        raise HTTPException(404,"Resumable upload session not found")
    created=session["created_at"]
    if isinstance(created,str):
        created=datetime.fromisoformat(created.replace("Z","+00:00"))
    if created.tzinfo is None:
        created=created.replace(tzinfo=timezone.utc)
    if (datetime.now(timezone.utc)-created).total_seconds()>24*60*60 and session["state"]=="OPEN":
        raise HTTPException(410,"Upload session expired. Begin a new secure transfer")
    return session


def _upload_parts(db,ctx,session_id):
    return _all(db,"""SELECT part_number,sha256,size_bytes,object_uri
      FROM external_provider_upload_parts WHERE amo_id=:amo
      AND tenant_provider_id=:provider AND session_id=:id ORDER BY part_number""",
      **ctx,id=session_id)


@partner_documents_router.post("/uploads",status_code=201)
def start_resumable_upload(tenant_slug:str,payload:UploadStart,request:Request,
                           db:Session=Depends(get_db)):
    user=partner._ctx(db,request,tenant_slug,cap="document.submit",write=True)
    if user["portal_state"]!="ACTIVE":
        raise HTTPException(403,"Suspended provider account may not start document intake")
    ctx=partner._context(user)
    auth.auth_limit(request,ctx["person"],"partner-document-upload-init")
    requirement=_requirement(db,ctx["amo"],ctx["supplier"],payload.requirement_id)
    if requirement["expiry_required"] and not payload.valid_until:
        raise HTTPException(422,"Expiry date required by tenant document policy")
    if payload.valid_until and payload.valid_until<date.today():
        raise HTTPException(422,"Expired evidence is not current")
    if payload.related_kind!="PROVIDER":
        partner._require_existing_related(db,user,payload.related_kind,payload.related_id or "")
        _governed_procurement_upload(db,user,payload.related_kind,payload.related_id or "")
    elif payload.related_id:
        raise HTTPException(422,"Provider-level evidence cannot refer to another record")
    original=Path(payload.filename).name
    if original!=payload.filename or not re.fullmatch(
        r"[\w.() -]{1,190}\.(pdf|docx|png|jpg|jpeg|txt)",original,re.I):
        raise HTTPException(415,"Invalid controlled original filename")
    suffix=Path(original).suffix.lower()
    if payload.content_type!=EXT_MIME.get(suffix):
        raise HTTPException(415,"Declared document MIME and filename must match")
    if payload.supersedes_submission_id:
        prior=_one(db,"""SELECT requirement_id,related_kind,related_id
          FROM external_partner_evidence_submissions WHERE amo_id=:amo
          AND tenant_provider_id=:provider AND id=:id""",
          **ctx,id=payload.supersedes_submission_id)
        if not prior or str(prior["requirement_id"])!=payload.requirement_id or (
            prior["related_kind"],prior["related_id"] or "")!=(
                payload.related_kind,payload.related_id or ""):
            raise HTTPException(422,"Replacement must match provider, scope and requirement")
    if requirement["acknowledgement_required"]:
        ack=_one(db,"""SELECT id FROM external_provider_form_acknowledgements
          WHERE amo_id=:amo AND tenant_provider_id=:provider AND identity_id=:person
          AND requirement_id=:req AND form_revision_id=:rev""",**ctx,
          req=payload.requirement_id,rev=requirement["form_revision_id"])
        if not ack:
            raise HTTPException(409,"Acknowledge the current controlled form before transferring")
    if requirement["form_revision_id"]:
        _published_revision(db,ctx["amo"],requirement["form_manual_id"],requirement["form_revision_id"])
    prior_session=_one(db,"""SELECT * FROM external_provider_upload_sessions
       WHERE amo_id=:amo AND tenant_provider_id=:provider AND identity_id=:person
       AND retry_key=:key""",**ctx,key=payload.retry_key)
    if prior_session:
        for field,expected in (("filename",original),("size_bytes",payload.size_bytes),
              ("requirement_id",payload.requirement_id),("related_kind",payload.related_kind),
              ("related_id",payload.related_id),("supersedes_submission_id",payload.supersedes_submission_id),
              ("valid_until",payload.valid_until),("sha256",payload.sha256 or "")):
            if prior_session[field]!=expected:
                raise HTTPException(409,"Retry key already belongs to a different upload")
        return {"id":prior_session["id"],"state":prior_session["state"],
                "chunk_size":PART_BYTES,"size_bytes":payload.size_bytes,
                "completed_submission_id":prior_session["completed_submission_id"]}
    session_id=str(uuid4())
    db.execute(text("""INSERT INTO external_provider_upload_sessions
      (id,amo_id,tenant_provider_id,identity_id,requirement_id,related_kind,related_id,
       supersedes_submission_id,filename,content_type,size_bytes,sha256,valid_until,retry_key)
      VALUES(:id,:amo,:provider,:person,:req,:kind,:related,:old,:filename,:mime,
       :size,:sha,:expiry,:retry)"""),
      {**ctx,"id":session_id,"req":payload.requirement_id,"kind":payload.related_kind,
       "related":payload.related_id,"old":payload.supersedes_submission_id,
       "filename":original,"mime":payload.content_type,"size":payload.size_bytes,
       "sha":payload.sha256 or "","expiry":payload.valid_until,"retry":payload.retry_key})
    auth.event(db,amo=ctx["amo"],identity=ctx["person"],grant=user["grant_id"],
      action="EXTERNAL_DOCUMENT_RESUMABLE_STARTED",actor_identity=ctx["person"],
      details={"session_id":session_id,"requirement_id":payload.requirement_id,"size_bytes":payload.size_bytes})
    db.commit()
    return {"id":session_id,"state":"OPEN","chunk_size":PART_BYTES,
            "size_bytes":payload.size_bytes,"completed_submission_id":None}


@partner_documents_router.get("/uploads/{session_id}")
def upload_progress(tenant_slug:str,session_id:str,request:Request,db:Session=Depends(get_db)):
    user=partner._ctx(db,request,tenant_slug,cap="document.submit")
    ctx=partner._context(user)
    session=_upload_session(db,ctx,session_id)
    parts=_upload_parts(db,ctx,session_id)
    return {"id":session_id,"state":session["state"],"chunk_size":PART_BYTES,
            "size_bytes":session["size_bytes"],"part_numbers":[p["part_number"] for p in parts],
            "bytes_received":sum(p["size_bytes"] for p in parts),
            "completed_submission_id":session["completed_submission_id"]}


@partner_documents_router.put("/uploads/{session_id}/parts/{part_number}")
async def upload_part(tenant_slug:str,session_id:str,part_number:int,request:Request,
                      db:Session=Depends(get_db)):
    user=partner._ctx(db,request,tenant_slug,cap="document.submit",write=True)
    ctx=partner._context(user)
    session=_upload_session(db,ctx,session_id,lock=True)
    if session["state"]!="OPEN":
        raise HTTPException(409,"Upload session no longer accepts parts")
    max_index=(session["size_bytes"]-1)//PART_BYTES
    if part_number<0 or part_number>max_index or max_index>=64:
        raise HTTPException(422,"Invalid upload part number")
    required_bytes=min(PART_BYTES,session["size_bytes"]-part_number*PART_BYTES)
    if request.headers.get("content-type","").split(";",1)[0].lower()!="application/octet-stream":
        raise HTTPException(415,"Resumable parts must use application/octet-stream")
    size=0;hashing=hashlib.sha256()
    with tempfile.NamedTemporaryFile(prefix="external-part-",suffix=".part") as tmp:
        async for chunk in request.stream():
            size+=len(chunk)
            if size>required_bytes:raise HTTPException(413,"Upload chunk exceeds its expected range")
            hashing.update(chunk);tmp.write(chunk)
        if size!=required_bytes:raise HTTPException(422,"Upload chunk length mismatch")
        checksum=hashing.hexdigest()
        existing=_one(db,"""SELECT sha256,size_bytes FROM external_provider_upload_parts
           WHERE amo_id=:amo AND tenant_provider_id=:provider
             AND session_id=:id AND part_number=:part""",
           **ctx,id=session_id,part=part_number)
        if existing:
            if existing["sha256"]!=checksum or existing["size_bytes"]!=size:
                raise HTTPException(409,"A different chunk already occupies this index")
            return {"part_number":part_number,"sha256":checksum,"accepted":True,"reused":True}
        tmp.flush()
        stored=storage.put_file(tmp.name,
           key=f"external-provider/uploads/{ctx['amo']}/{ctx['provider']}/{session_id}/{part_number}-{uuid4().hex}",
           content_type="application/octet-stream")
    try:
        db.execute(text("""INSERT INTO external_provider_upload_parts
          (id,amo_id,tenant_provider_id,session_id,part_number,object_uri,size_bytes,sha256)
          VALUES(:id,:amo,:provider,:session,:part,:uri,:size,:sha)"""),
          {**ctx,"id":str(uuid4()),"session":session_id,"part":part_number,
           "uri":stored.uri,"size":size,"sha":checksum})
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(stored.uri)
        raise
    return {"part_number":part_number,"sha256":checksum,"accepted":True,"reused":False}


@partner_documents_router.post("/uploads/{session_id}/complete")
def complete_resumable_upload(tenant_slug:str,session_id:str,request:Request,
                              db:Session=Depends(get_db)):
    user=partner._ctx(db,request,tenant_slug,cap="document.submit",write=True)
    ctx=partner._context(user)
    session=_upload_session(db,ctx,session_id,lock=True)
    if session["state"]=="COMPLETED":
        return {"id":session["completed_submission_id"],"status":"PENDING_REVIEW","retry":True}
    if session["state"]!="OPEN":
        raise HTTPException(409,"Upload session is not open")
    requirement=_requirement(db,ctx["amo"],ctx["supplier"],session["requirement_id"])
    if requirement["form_revision_id"]:
        _published_revision(db,ctx["amo"],requirement["form_manual_id"],requirement["form_revision_id"])
    if requirement["acknowledgement_required"]:
        ack=_one(db,"""SELECT id FROM external_provider_form_acknowledgements
          WHERE amo_id=:amo AND tenant_provider_id=:provider AND identity_id=:person
          AND requirement_id=:req AND form_revision_id=:rev""",**ctx,
          req=session["requirement_id"],rev=requirement["form_revision_id"])
        if not ack:raise HTTPException(409,"Controlled form acknowledgement no longer valid")
    if session["related_kind"]!="PROVIDER":
        partner._require_existing_related(db,user,session["related_kind"],session["related_id"])
        _governed_procurement_upload(db,user,session["related_kind"],session["related_id"])
    parts=_upload_parts(db,ctx,session_id)
    expected_count=(session["size_bytes"]+PART_BYTES-1)//PART_BYTES
    if len(parts)!=expected_count or [p["part_number"] for p in parts]!=list(range(expected_count)):
        raise HTTPException(409,"Upload is incomplete; resume missing chunks")
    sha=hashlib.sha256();size=0
    suffix=Path(session["filename"]).suffix.lower()
    stored=None
    with tempfile.NamedTemporaryFile(prefix="external-reassembled-",suffix=suffix) as tmp:
        for part in parts:
            source=storage.materialize(part["object_uri"],expected_sha256=part["sha256"])
            with open(source,"rb") as file:
                while chunk:=file.read(1024*1024):
                    size+=len(chunk);sha.update(chunk);tmp.write(chunk)
        if size!=session["size_bytes"] or (session["sha256"] and sha.hexdigest()!=session["sha256"]):
            raise HTTPException(409,"Reassembled file failed expected size or original checksum")
        tmp.flush()
        _validate_file(Path(tmp.name),session["filename"],session["content_type"])
        _scan_clamd(tmp.name)
        record=str(uuid4())
        stored=storage.put_file(tmp.name,
            key=f"external-provider/{ctx['amo']}/{ctx['supplier']}/{record}{suffix}",
            content_type=session["content_type"])
    try:
        db.execute(text("""INSERT INTO external_partner_evidence_submissions
          (id,amo_id,tenant_provider_id,identity_id,evidence_type,related_kind,related_id,
           filename,content_type,object_uri,sha256,size_bytes,requirement_id,
           supersedes_submission_id,form_revision_id,valid_until,idempotency_key)
          VALUES(:id,:amo,:provider,:person,:type,:kind,:related,:filename,:mime,:uri,:sha,:size,
           :req,:old,:form,:expiry,:retry)"""),
           {**ctx,"id":record,"type":requirement["code"],"kind":session["related_kind"],
            "related":session["related_id"],"filename":session["filename"],
            "mime":session["content_type"],"uri":stored.uri,"sha":sha.hexdigest(),
            "size":size,"req":session["requirement_id"],"old":session["supersedes_submission_id"],
            "form":requirement["form_revision_id"],"expiry":session["valid_until"],
            "retry":session["retry_key"]})
        db.execute(text("""UPDATE external_provider_upload_sessions
          SET state='COMPLETED',completed_submission_id=:submission,updated_at=NOW()
          WHERE amo_id=:amo AND tenant_provider_id=:provider AND id=:id"""),
          {**ctx,"id":session_id,"submission":record})
        _event(db,ctx["amo"],record,"RECEIVED",identity=ctx["person"],
            details={"sha256":sha.hexdigest(),"size":size,
                "requirement_id":session["requirement_id"],"resumable_session_id":session_id,
                "chunk_checksums":[p["sha256"] for p in parts]})
        auth.event(db,amo=ctx["amo"],identity=ctx["person"],grant=user["grant_id"],
          action="EXTERNAL_DOCUMENT_STAGED",actor_identity=ctx["person"],
          details={"submission":record,"session_id":session_id,"sha256":sha.hexdigest()})
        db.commit()
    except Exception:
        db.rollback()
        if stored is not None:storage.delete(stored.uri)
        raise
    # The canonical object is intact; temporary remote chunks can be reclaimed.
    for part in parts:
        try:storage.delete(part["object_uri"])
        except (OSError,RuntimeError):pass
    return {"id":record,"status":"PENDING_REVIEW","sha256":sha.hexdigest(),
            "size_bytes":size,"resumable_session_id":session_id}


@partner_documents_router.get("/assignment-scopes")
def assignment_scopes(tenant_slug:str,request:Request,db:Session=Depends(get_db)):
    """Expose only the audit assignment identifiers expressly granted to this member."""
    user=partner._ctx(db,request,tenant_slug,cap="document.read")
    allowed=sorted(partner._allowed(user,"assignments"))
    return {"items":[{"id":value} for value in allowed[:100]]}


class FormAttestation(BaseModel):
    accepted: Literal[True]
    declaration: str = Field(min_length=12,max_length=500)


@partner_documents_router.post("/requirements/{requirement_id}/acknowledge")
def acknowledge_form(tenant_slug:str,requirement_id:str,payload:FormAttestation,
                     request:Request,db:Session=Depends(get_db)):
    user=partner._ctx(db,request,tenant_slug,cap="document.read",write=True)
    ctx=partner._context(user)
    requirement=_requirement(db,ctx["amo"],ctx["supplier"],requirement_id)
    if not requirement["acknowledgement_required"] or not requirement["form_revision_id"]:
        raise HTTPException(409,"No controlled-form acknowledgement is required")
    partner._require_object(user,"documents",str(requirement["form_manual_id"]))
    _published_revision(db,ctx["amo"],requirement["form_manual_id"],requirement["form_revision_id"])
    prior=_one(db,"""SELECT id FROM external_provider_form_acknowledgements
      WHERE amo_id=:amo AND tenant_provider_id=:provider AND identity_id=:person
      AND requirement_id=:req AND form_revision_id=:revision""",
      amo=ctx["amo"],provider=ctx["provider"],person=ctx["person"],
      req=requirement_id,revision=requirement["form_revision_id"])
    if prior:
        return {"id":prior["id"],"acknowledged":True,"revision_id":requirement["form_revision_id"]}
    ack_id=str(uuid4())
    db.execute(text("""INSERT INTO external_provider_form_acknowledgements
      (id,amo_id,tenant_provider_id,identity_id,requirement_id,form_revision_id,attestation)
      VALUES(:id,:amo,:provider,:person,:req,:revision,:declaration)"""),
      {**ctx,"id":ack_id,"req":requirement_id,"revision":requirement["form_revision_id"],
       "declaration":payload.declaration.strip()})
    auth.event(db,amo=ctx["amo"],identity=ctx["person"],grant=user["grant_id"],
      action="CONTROLLED_FORM_ACKNOWLEDGED",actor_identity=ctx["person"],
      details={"requirement_id":requirement_id,"revision_id":requirement["form_revision_id"],
               "acknowledgement_id":ack_id})
    db.commit()
    return {"id":ack_id,"acknowledged":True,"revision_id":requirement["form_revision_id"]}


@partner_documents_router.get("/submissions")
def my_submissions(tenant_slug:str,request:Request,db:Session=Depends(get_db),
                    limit:int=Query(25,ge=1,le=50),offset:int=Query(0,ge=0,le=10000)):
    user=partner._ctx(db,request,tenant_slug,cap="document.read")
    ctx=partner._context(user)
    scopes={"contracts":sorted(partner._allowed(user,"contracts")),
            "assignments":sorted(partner._allowed(user,"assignments")),
            "rfqs":sorted(partner._allowed(user,"rfqs")),
            "pos":sorted(partner._allowed(user,"purchase_orders")),
            "work":sorted(partner._allowed(user,"contracted_work"))}
    sql=text("""SELECT s.id,s.filename,s.evidence_type,s.status,s.related_kind,s.related_id,
       s.requirement_id,s.form_revision_id,s.supersedes_submission_id,s.valid_until,
       s.created_at,s.review_note,s.reviewed_at,s.qms_evidence_id,s.dms_revision_id,s.sha256
       FROM external_partner_evidence_submissions s
       WHERE s.amo_id=:amo AND s.tenant_provider_id=:provider
       AND (s.related_kind='PROVIDER' OR
           (s.related_kind='CONTRACT' AND s.related_id IN :contracts) OR
           (s.related_kind='ASSIGNMENT' AND s.related_id IN :assignments) OR
           (s.related_kind='CONTRACTED_WORK' AND s.related_id IN :work) OR
           (s.related_kind='RFQ' AND s.related_id IN :rfqs) OR
           (s.related_kind='PO' AND s.related_id IN :pos) OR
           (s.related_kind='SHIPMENT' AND EXISTS (
               SELECT 1 FROM external_procurement_shipments sh WHERE sh.id=s.related_id
               AND sh.amo_id=s.amo_id AND sh.supplier_id=:supplier
               AND CAST(sh.po_id AS TEXT) IN :pos)))
       ORDER BY s.created_at DESC,s.id DESC LIMIT :limit OFFSET :offset""").bindparams(
           bindparam("contracts",expanding=True),bindparam("assignments",expanding=True),
           bindparam("rfqs",expanding=True),bindparam("pos",expanding=True),
           bindparam("work",expanding=True))
    items=[dict(x) for x in db.execute(sql,{**ctx,**scopes,"limit":limit,"offset":offset}).mappings()]
    return {"items":items,"limit":limit,"offset":offset,"has_more":len(items)==limit}


@partner_documents_router.post("/submissions",status_code=201)
def submit_document(tenant_slug:str,request:Request,db:Session=Depends(get_db),
                    file:UploadFile=File(...),requirement_id:str=Form(...),
                    related_kind:Literal["PROVIDER","CONTRACT","ASSIGNMENT","RFQ","PO","SHIPMENT","CONTRACTED_WORK"]=Form("PROVIDER"),
                    related_id:str=Form(""),supersedes_submission_id:str=Form(""),
                    valid_until:date|None=Form(None),
                    idempotency_key:str=Form(...)):
    user=partner._ctx(db,request,tenant_slug,cap="document.submit",write=True)
    if user["portal_state"]!="ACTIVE":
        raise HTTPException(403,"Suspended external accounts cannot submit new documents")
    ctx=partner._context(user)
    auth.auth_limit(request,ctx["person"],"partner-document-submit")
    requirement=_requirement(db,ctx["amo"],ctx["supplier"],requirement_id)
    if requirement["acknowledgement_required"]:
        acknowledged=_one(db,"""SELECT id FROM external_provider_form_acknowledgements
           WHERE amo_id=:amo AND tenant_provider_id=:provider AND identity_id=:person
             AND requirement_id=:req AND form_revision_id=:revision""",
           amo=ctx["amo"],provider=ctx["provider"],person=ctx["person"],
           req=requirement_id,revision=requirement["form_revision_id"])
        if not acknowledged:
            raise HTTPException(409,"Acknowledge this exact controlled form revision before submitting")
    if requirement["expiry_required"] and not valid_until:
        raise HTTPException(422,"This requirement needs an expiry date")
    if valid_until and valid_until<date.today():
        raise HTTPException(422,"Expired evidence cannot be submitted as current")
    if related_kind!="PROVIDER":
        partner._require_existing_related(db,user,related_kind,related_id)
        _governed_procurement_upload(db,user,related_kind,related_id)
    elif related_id:
        raise HTTPException(422,"Provider-level documents must not specify a related record")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{12,64}",idempotency_key):
        raise HTTPException(422,"Invalid upload retry key")
    original=Path(file.filename or "").name
    if original!=file.filename or not re.fullmatch(r"[\w.() -]{1,190}\.(pdf|docx|png|jpg|jpeg|txt)",original,re.I):
        raise HTTPException(415,"Invalid or unsafe document filename")
    if supersedes_submission_id:
        previous=_one(db,"""SELECT id,requirement_id,related_kind,related_id,status
          FROM external_partner_evidence_submissions
          WHERE amo_id=:amo AND tenant_provider_id=:provider AND id=:id""",
          amo=ctx["amo"],provider=ctx["provider"],id=supersedes_submission_id)
        if not previous or str(previous["requirement_id"])!=requirement_id or (
            previous["related_kind"],previous["related_id"] or "")!=(related_kind,related_id or ""):
            raise HTTPException(422,"Resubmission must replace an earlier document for the same requirement and scope")
    existing=_one(db,"""SELECT id,status,filename FROM external_partner_evidence_submissions
       WHERE amo_id=:amo AND tenant_provider_id=:provider AND idempotency_key=:key""",
       amo=ctx["amo"],provider=ctx["provider"],key=idempotency_key)
    if existing:
        return {"id":existing["id"],"filename":existing["filename"],"status":existing["status"],"retry":True}
    # Record exact current DMS form source before receiving provider responses.
    form_id=requirement["form_revision_id"]
    if form_id:
        _published_revision(db,ctx["amo"],requirement["form_manual_id"],form_id)
    sha=hashlib.sha256();size=0
    suffix=Path(original).suffix.lower()
    with tempfile.NamedTemporaryFile(prefix="external-intake-",suffix=suffix) as handle:
        while chunk:=file.file.read(1024*1024):
            size+=len(chunk)
            if size>MAX_FILE_BYTES:
                raise HTTPException(413,"File exceeds tenant intake limit of 20 MB")
            sha.update(chunk);handle.write(chunk)
        if size==0:raise HTTPException(422,"Empty document")
        handle.flush()
        _validate_file(Path(handle.name),original,file.content_type or "")
        _scan_clamd(handle.name)
        record=str(uuid4())
        stored=storage.put_file(handle.name,
           key=f"external-provider/{ctx['amo']}/{ctx['supplier']}/{record}{suffix}",
           content_type=EXT_MIME[suffix])
    try:
        db.execute(text("""INSERT INTO external_partner_evidence_submissions
          (id,amo_id,tenant_provider_id,identity_id,evidence_type,related_kind,related_id,
           filename,content_type,object_uri,sha256,size_bytes,requirement_id,
           supersedes_submission_id,form_revision_id,valid_until,idempotency_key)
          VALUES(:id,:amo,:provider,:person,:type,:kind,:related,:filename,:mime,:uri,:sha,:size,
            :requirement,:previous,:form,:expiry,:key)"""),
          {**ctx,"id":record,"type":requirement["code"],"kind":related_kind,
           "related":related_id or None,"filename":original,"mime":EXT_MIME[suffix],
           "uri":stored.uri,"sha":sha.hexdigest(),"size":size,"requirement":requirement_id,
           "previous":supersedes_submission_id or None,"form":form_id,
           "expiry":valid_until,"key":idempotency_key})
        _event(db,ctx["amo"],record,"RECEIVED",identity=ctx["person"],
               details={"sha256":sha.hexdigest(),"size":size,"requirement_id":requirement_id,
                        "form_revision_id":form_id,"supersedes":supersedes_submission_id or None})
        auth.event(db,amo=ctx["amo"],identity=ctx["person"],grant=user["grant_id"],
           action="EXTERNAL_DOCUMENT_STAGED",actor_identity=ctx["person"],
           details={"submission":record,"requirement":requirement_id,"sha256":sha.hexdigest()})
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(stored.uri)
        raise
    return {"id":record,"filename":original,"sha256":sha.hexdigest(),"status":"PENDING_REVIEW"}


@partner_documents_router.get("/submissions/{submission_id}/original")
def download_my_original(tenant_slug:str,submission_id:str,request:Request,db:Session=Depends(get_db)):
    user=partner._ctx(db,request,tenant_slug,cap="document.read")
    ctx=partner._context(user)
    row=_one(db,"""SELECT object_uri,sha256,content_type,filename,related_kind,related_id
       FROM external_partner_evidence_submissions
       WHERE amo_id=:amo AND tenant_provider_id=:provider AND id=:id""",
       amo=ctx["amo"],provider=ctx["provider"],id=submission_id)
    if not row:raise HTTPException(404,"Submission unavailable")
    if row["related_kind"] in {"CONTRACT","ASSIGNMENT","RFQ","PO","SHIPMENT","CONTRACTED_WORK"}:
        partner._require_existing_related(db,user,row["related_kind"],row["related_id"])
    file=storage.materialize(row["object_uri"],expected_sha256=row["sha256"])
    return FileResponse(file,filename=row["filename"],media_type=row["content_type"],
        headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})


class AgreementControls(BaseModel):
    expected_version: int = Field(ge=1)
    counterparties: list[str] = Field(min_length=2,max_length=8)
    approved_sites: list[str] = Field(default_factory=list,max_length=100)
    authority_acceptance_reference: str | None = Field(default=None,max_length=255)
    controlled_document_id: str = Field(min_length=8,max_length=36)
    controlled_document_revision: str = Field(min_length=8,max_length=36)
    signed_evidence_submission_id: str = Field(min_length=8,max_length=36)
    renewal_terms: str | None = Field(default=None,max_length=4000)
    termination_notice_days: int | None = Field(default=None,ge=0,le=3650)


@staff_documents_router.get("/contracts/{contract_id}/controls")
def agreement_controls(amo_code:str,contract_id:str,db:Session=Depends(get_db),
                       user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    row=_one(db,"""SELECT id,supplier_id,contract_number,status,version,scope_text,
        effective_on,expires_on,counterparties_json,approved_sites_json,
        authority_acceptance_reference,controlled_document_id,controlled_document_revision,
        signed_evidence_submission_id,renewal_terms,termination_notice_days
        FROM quality_external_provider_contracts WHERE amo_id=:amo AND id=:id""",
        amo=amo,id=contract_id)
    if not row:raise HTTPException(404,"Agreement not found")
    return row


@staff_documents_router.get("/contracts/{contract_id}/candidate-evidence")
def agreement_candidate_evidence(amo_code:str,contract_id:str,db:Session=Depends(get_db),
                                 user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    agreement=_one(db,"""SELECT supplier_id FROM quality_external_provider_contracts
       WHERE amo_id=:amo AND id=:id""",amo=amo,id=contract_id)
    if not agreement:raise HTTPException(404,"Agreement unavailable")
    return {"items":_all(db,"""SELECT e.id,e.filename,e.sha256,e.created_at,
        e.status,q.status AS quality_status
        FROM external_partner_evidence_submissions e
        JOIN external_tenant_providers p ON p.id=e.tenant_provider_id AND p.amo_id=e.amo_id
        LEFT JOIN quality_external_provider_evidence q ON q.amo_id=e.amo_id AND q.id=e.qms_evidence_id
        WHERE e.amo_id=:amo AND p.supplier_id=:supplier AND e.related_kind='CONTRACT'
          AND e.related_id=:contract AND e.status='ACCEPTED'
        ORDER BY e.created_at DESC LIMIT 100""",amo=amo,supplier=agreement["supplier_id"],
        contract=contract_id)}


@staff_documents_router.patch("/contracts/{contract_id}/controls")
def update_agreement_controls(amo_code:str,contract_id:str,payload:AgreementControls,
                              db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user,True)
    row=_one(db,"""SELECT * FROM quality_external_provider_contracts
        WHERE amo_id=:amo AND id=:id FOR UPDATE""",amo=amo,id=contract_id)
    if not row:raise HTTPException(404,"Agreement not found")
    if row["status"]!="DRAFT":
        raise HTTPException(409,"Executed agreement records are immutable; create a controlled amendment or renewal")
    if row["version"]!=payload.expected_version:
        raise HTTPException(409,"Agreement version changed; reload before updating")
    if any(not 2<=len(s.strip())<=150 for s in payload.counterparties):
        raise HTTPException(422,"Two or more identified contracting parties are required")
    if any(not 1<=len(s.strip())<=100 for s in payload.approved_sites):
        raise HTTPException(422,"Invalid approved site identifier")
    published=_staff_published_revision(db,amo,payload.controlled_document_id,
                                   payload.controlled_document_revision,user)
    signed=_one(db,"""SELECT e.id,e.sha256,e.status,e.qms_evidence_id,
           q.status AS quality_state
           FROM external_partner_evidence_submissions e
           JOIN external_tenant_providers p ON p.amo_id=e.amo_id AND p.id=e.tenant_provider_id
           LEFT JOIN quality_external_provider_evidence q
              ON q.amo_id=e.amo_id AND q.id=e.qms_evidence_id
           WHERE e.amo_id=:amo AND e.id=:id AND p.supplier_id=:supplier
             AND e.related_kind='CONTRACT' AND e.related_id=:contract""",
             amo=amo,id=payload.signed_evidence_submission_id,
             supplier=row["supplier_id"],contract=contract_id)
    if not signed or signed["status"]!="ACCEPTED" or signed["sha256"]!=published["source_sha256"]:
        raise HTTPException(409,"Signed agreement must be accepted controlled evidence with an exact DMS source hash")
    db.execute(text("""UPDATE quality_external_provider_contracts
       SET counterparties_json=CAST(:parties AS JSON),approved_sites_json=CAST(:sites AS JSON),
           authority_acceptance_reference=:authority,
           controlled_document_id=:manual,controlled_document_revision=:revision,
           signed_evidence_submission_id=:signed,
           renewal_terms=:renewal,termination_notice_days=:notice,
           version=version+1,updated_at=NOW(),updated_by_user_id=:actor
       WHERE amo_id=:amo AND id=:id"""),
       {"parties":json.dumps([s.strip() for s in payload.counterparties]),
        "sites":json.dumps(sorted(set(s.strip() for s in payload.approved_sites))),
        "authority":payload.authority_acceptance_reference,"manual":payload.controlled_document_id,
        "revision":payload.controlled_document_revision,"signed":payload.signed_evidence_submission_id,
        "renewal":payload.renewal_terms,"notice":payload.termination_notice_days,
        "actor":str(user.id),"amo":amo,"id":contract_id})
    auth.event(db,amo=amo,identity=None,grant=None,actor_user=str(user.id),
       action="PROVIDER_AGREEMENT_CONTROLS_UPDATED",
       details={"contract_id":contract_id,"previous_version":row["version"],
                "dms_revision":payload.controlled_document_revision,
                "signed_submission":payload.signed_evidence_submission_id,
                "evidence_quality_state":signed["quality_state"]})
    db.commit()
    return {"id":contract_id,"version":row["version"]+1,
            "quality_authorization_conferred":False,"commercial_status":"DRAFT"}


@staff_documents_router.get("/dms-options")
def dms_options(amo_code:str,db:Session=Depends(get_db),
                user=Depends(get_current_active_user),
                limit:int=Query(50,ge=1,le=100)):
    amo=_staff(db,amo_code,user)
    from amodb.apps.doc_control import domain_models as dms_models
    from amodb.apps.doc_control.workspace_service import can_read_manual
    raw=_all(db,"""SELECT m.id,m.code,m.title,r.id AS revision_id,r.rev_number
        FROM manuals m JOIN manual_tenants t ON t.id=m.tenant_id
        JOIN manual_revisions r ON r.id=m.current_published_rev_id AND r.manual_id=m.id
        WHERE t.amo_id=:amo AND r.status_enum='PUBLISHED' AND r.published_at IS NOT NULL
          AND r.source_storage_path IS NOT NULL
        ORDER BY m.code,r.rev_number LIMIT 500""",amo=amo)
    manual_ids=[manual["id"] for manual in raw]
    profiles=db.query(dms_models.DocumentControlProfile).filter(
        dms_models.DocumentControlProfile.tenant_id==amo,
        dms_models.DocumentControlProfile.manual_id.in_(manual_ids)).all() if manual_ids else []
    by_id={str(p.manual_id):p for p in profiles}
    accessible=[]
    for manual in raw:
        if can_read_manual(user,by_id.get(str(manual["id"]))):
            accessible.append(manual)
            if len(accessible)>=limit:break
    return {"items":accessible}


@staff_documents_router.get("/submissions")
def queue(amo_code:str,db:Session=Depends(get_db),user=Depends(get_current_active_user),
          limit:int=Query(25,ge=1,le=50),offset:int=Query(0,ge=0,le=10000)):
    amo=_staff(db,amo_code,user)
    rows=_all(db,"""SELECT s.id,s.filename,s.status,s.evidence_type,s.related_kind,s.related_id,
      s.tenant_provider_id,s.requirement_id,s.supersedes_submission_id,s.form_revision_id,
      s.sha256,s.size_bytes,s.valid_until,s.dms_revision_id,s.qms_evidence_id,
      s.review_note,s.created_at,s.dms_evidence_asset_id,s.dms_retention_id,
      (SELECT MAX(a.occurred_at) FROM external_provider_form_acknowledgements a
       WHERE a.amo_id=s.amo_id AND a.tenant_provider_id=s.tenant_provider_id
         AND a.identity_id=s.identity_id AND a.requirement_id=s.requirement_id
         AND a.form_revision_id=s.form_revision_id) AS form_acknowledged_at,
      r.title AS requirement_title,p.supplier_id,
      v.legal_name,i.email,
      d.status AS dms_retention_status,d.legal_hold AS dms_legal_hold,
      d.retention_until AS dms_retention_until
      FROM external_partner_evidence_submissions s
      JOIN external_tenant_providers p ON p.id=s.tenant_provider_id AND p.amo_id=s.amo_id
      JOIN procurement_suppliers v ON v.amo_id=p.amo_id AND v.id=p.supplier_id
      JOIN external_identities i ON i.id=s.identity_id
      LEFT JOIN external_provider_document_requirements r ON r.amo_id=s.amo_id AND r.id=s.requirement_id
      LEFT JOIN document_retention_dispositions d ON d.tenant_id=s.amo_id
        AND d.id=s.dms_retention_id
      WHERE s.amo_id=:amo ORDER BY s.created_at DESC,s.id DESC
      LIMIT :limit OFFSET :offset""",amo=amo,limit=limit,offset=offset)
    return {"items":rows,"limit":limit,"offset":offset,"has_more":len(rows)==limit}


class Review(BaseModel):
    decision: Literal["ACCEPTED","RETURNED","REJECTED"]
    reason: str = Field(min_length=8,max_length=2000)
    dms_manual_id: str | None = Field(default=None,max_length=36)
    dms_revision_id: str | None = Field(default=None,max_length=36)


@staff_documents_router.post("/submissions/{submission_id}/review")
def review(amo_code:str,submission_id:str,payload:Review,db:Session=Depends(get_db),
           user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    # Quality owns acceptance/rejection and the transition into QMS evidence.
    # Document Control may register a reviewed original but never decide Quality.
    if str(getattr(user.role,"value",user.role)) not in {"QUALITY_MANAGER","QUALITY_OFFICER"}:
        raise HTTPException(403,"Only appointed Quality staff may decide provider evidence intake")
    row=_one(db,"""SELECT s.*,p.supplier_id FROM external_partner_evidence_submissions s
      JOIN external_tenant_providers p ON p.id=s.tenant_provider_id AND p.amo_id=s.amo_id
      WHERE s.amo_id=:amo AND s.id=:id FOR UPDATE""",amo=amo,id=submission_id)
    if not row:raise HTTPException(404,"Submission unavailable")
    if row["status"]!="PENDING_REVIEW":
        raise HTTPException(409,"Only unreviewed submissions can receive a new decision")
    if not row["requirement_id"]:
        raise HTTPException(409,"Historical unclassified submissions require manual migration into a configured, controlled requirement; no approval bypass")
    req=_one(db,"""SELECT id,enabled,code FROM external_provider_document_requirements
        WHERE amo_id=:amo AND id=:id""",amo=amo,id=row["requirement_id"])
    if not req or (not req["enabled"] and payload.decision=="ACCEPTED"):
        raise HTTPException(409,"Document requirement is no longer valid for acceptance")
    # A document that expired while queued must not enter the accepted QMS register.
    # Reviewers may still return or reject it and preserve the original and history.
    if (payload.decision=="ACCEPTED" and row["valid_until"] is not None
            and row["valid_until"] < date.today()):
        raise HTTPException(409,"Expired evidence cannot be accepted; request a current replacement")
    if bool(payload.dms_manual_id)!=bool(payload.dms_revision_id):
        raise HTTPException(422,"DMS references require both manual and exact revision IDs")
    if payload.decision!="ACCEPTED" and payload.dms_manual_id:
        raise HTTPException(422,"A DMS attachment is only set at acceptance")
    if payload.dms_manual_id:
        published=_staff_published_revision(db,amo,payload.dms_manual_id,payload.dms_revision_id,user)
        if published["source_sha256"]!=row["sha256"]:
            raise HTTPException(409,"The controlled DMS revision must have the same original-file SHA-256 as the staged submission")
    qms_id=None
    if payload.decision=="ACCEPTED":
        # Quality evidence is only PENDING. Verification must pass separately
        # through the authoritative QMS evidence decision endpoint.
        qms_id=str(uuid4())
        if row["related_kind"]=="CONTRACT":
            contract=_one(db,"""SELECT id FROM quality_external_provider_contracts
                 WHERE amo_id=:amo AND supplier_id=:supplier AND id=:id""",
                 amo=amo,supplier=row["supplier_id"],id=row["related_id"])
            if not contract:raise HTTPException(409,"Agreement no longer belongs to this provider")
        db.execute(text("""INSERT INTO quality_external_provider_evidence
          (id,amo_id,supplier_id,contract_id,evidence_type,source_system,source_id,
           title,status,valid_until,notes,created_by_user_id)
          VALUES(:id,:amo,:supplier,:contract,:type,'EXTERNAL_PROVIDER_STAGING',:source,
             :title,'PENDING',:expiry,:notes,:actor)"""),
          {"id":qms_id,"amo":amo,"supplier":row["supplier_id"],
           "contract":row["related_id"] if row["related_kind"]=="CONTRACT" else None,
           "type":row["evidence_type"],"source":submission_id,"title":row["filename"],
           "expiry":row["valid_until"],"notes":payload.reason,"actor":str(user.id)})
    db.execute(text("""UPDATE external_partner_evidence_submissions
       SET status=:state,review_note=:reason,reviewed_by_user_id=:actor,reviewed_at=NOW(),
           dms_manual_id=:manual,dms_revision_id=:revision,qms_evidence_id=:qms
       WHERE amo_id=:amo AND id=:id"""),
       {"state":payload.decision,"reason":payload.reason,"actor":str(user.id),"amo":amo,
        "id":submission_id,"manual":payload.dms_manual_id,"revision":payload.dms_revision_id,"qms":qms_id})
    _event(db,amo,submission_id,"REVIEW_"+payload.decision,actor=str(user.id),
       details={"reason":payload.reason,"dms_revision":payload.dms_revision_id,
                "qms_evidence_id":qms_id,"qms_state":"PENDING" if qms_id else None})
    db.execute(text("""INSERT INTO external_partner_notifications
        (id,amo_id,tenant_provider_id,identity_id,category,title,message,resource_kind,resource_id)
        VALUES(:id,:amo,:provider,:identity,'EVIDENCE',:title,:message,'EVIDENCE',:submission)"""),
        {"id":str(uuid4()),"amo":amo,"provider":row["tenant_provider_id"],
         "identity":row["identity_id"],"title":"Document review outcome",
         "message":f"{payload.decision}: {payload.reason[:200]}",
         "submission":submission_id})
    auth.event(db,amo=amo,identity=row["identity_id"],grant=None,actor_user=str(user.id),
       action="EXTERNAL_DOCUMENT_REVIEWED",
       details={"submission":submission_id,"decision":payload.decision,"qms_evidence":qms_id})
    db.commit()
    return {"id":submission_id,"status":payload.decision,"qms_evidence_id":qms_id,
            "quality_verified":False,"dms_revision_id":payload.dms_revision_id}


class DmsRegistration(BaseModel):
    manual_id: str = Field(min_length=8,max_length=36)
    retention_class: str = Field(min_length=1,max_length=64)
    retention_until: datetime | None = None
    reason: str = Field(min_length=8,max_length=2000)


@staff_documents_router.post("/submissions/{submission_id}/register-dms")
def register_dms_evidence(amo_code:str,submission_id:str,payload:DmsRegistration,
                          request:Request,db:Session=Depends(get_db),
                          user=Depends(get_current_active_user)):
    """DCO-only handoff of the exact original into existing DMS asset/retention controls."""
    amo=_staff(db,amo_code,user)
    from amodb.apps.doc_control import evidence_models as em, retention_models as rm
    from amodb.apps.doc_control import workspace_evidence_router as wer
    from amodb.apps.doc_control.workspace_service import (
        require_control_user, resolve_tenant, get_manual, get_profile,
        require_manual_access, audit)
    require_control_user(user)
    tenant_row=_one(db,"SELECT slug FROM manual_tenants WHERE amo_id=:amo",amo=amo)
    if not tenant_row:
        raise HTTPException(404,"Tenant Document Control workspace unavailable")
    dms_tenant=resolve_tenant(db,tenant_row["slug"],user)
    manual=get_manual(db,dms_tenant,payload.manual_id)
    require_manual_access(user,get_profile(db,dms_tenant,manual.id))
    revision=_one(db,"""SELECT r.id FROM manual_revisions r JOIN manuals m
      ON m.id=r.manual_id WHERE m.id=:manual AND r.id=m.current_published_rev_id
      AND r.status_enum='PUBLISHED' AND r.published_at IS NOT NULL""",manual=manual.id)
    if not revision:
        raise HTTPException(409,"Select a DMS manual with a current published revision")
    row=_one(db,"""SELECT s.*,p.supplier_id FROM external_partner_evidence_submissions s
      JOIN external_tenant_providers p ON p.amo_id=s.amo_id AND p.id=s.tenant_provider_id
      WHERE s.amo_id=:amo AND s.id=:id FOR UPDATE""",amo=amo,id=submission_id)
    if not row:
        raise HTTPException(404,"Provider evidence unavailable")
    if row["dms_evidence_asset_id"] or row["dms_retention_id"]:
        raise HTTPException(409,"Original already governed by Document Control")
    if row["status"]=="PENDING_REVIEW":
        raise HTTPException(409,"Complete intake review before registration")
    source=storage.materialize(row["object_uri"],expected_sha256=row["sha256"])
    asset_id=str(uuid4());retention_id=str(uuid4())
    root=wer.EVIDENCE_ROOT
    destination=(root / str(dms_tenant.slug).lower() / str(manual.id) /
                 "provider-evidence" / (asset_id+"_"+Path(row["filename"]).name)).resolve()
    if root not in destination.parents:
        raise HTTPException(500,"Invalid Document Control evidence path")
    destination.parent.mkdir(parents=True,exist_ok=True)
    try:
        shutil.copyfile(source,destination)
        with destination.open("rb") as checked:
            retained_hash=hashlib.file_digest(checked,"sha256").hexdigest()
        if retained_hash!=row["sha256"]:
            raise HTTPException(409,"Retained DMS original failed checksum verification")
        until=payload.retention_until
        retention_state="DUE" if until and until<=datetime.now(timezone.utc) else "ACTIVE"
        db.add(em.DocumentEvidenceAsset(
            id=asset_id,tenant_id=amo,manual_id=manual.id,revision_id=revision["id"],
            category="EXTERNAL_SOURCE",purpose="External provider controlled submission",
            filename=row["filename"],mime_type=row["content_type"],
            size_bytes=row["size_bytes"],sha256=row["sha256"],storage_path=str(destination),
            description=payload.reason,uploaded_by_user_id=str(user.id),
            source_context_json={"external_provider_submission_id":submission_id,
                "tenant_provider_id":row["tenant_provider_id"],
                "supplier_id":row["supplier_id"],"requirement_id":row["requirement_id"],
                "source_sha256":row["sha256"]}))
        db.add(rm.DocumentRetentionDisposition(
            id=retention_id,tenant_id=amo,manual_id=manual.id,revision_id=revision["id"],
            source_type="EVIDENCE_ASSET",source_id=asset_id,
            source_label=row["filename"],retention_class=payload.retention_class.strip().upper(),
            retention_until=until,status=retention_state,legal_hold=False,
            created_by_user_id=str(user.id),
            metadata_json={"provider_submission_id":submission_id,
                           "source_sha256":row["sha256"],"reason":payload.reason}))
        db.flush()
        db.execute(text("""UPDATE external_partner_evidence_submissions
            SET dms_evidence_asset_id=:asset,dms_retention_id=:retention
            WHERE amo_id=:amo AND id=:id"""),
            {"asset":asset_id,"retention":retention_id,"amo":amo,"id":submission_id})
        _event(db,amo,submission_id,"DMS_RETENTION_REGISTERED",actor=str(user.id),
            details={"asset_id":asset_id,"retention_id":retention_id,
                     "manual_id":manual.id,"retention_class":payload.retention_class,
                     "retention_until":until.isoformat() if until else None})
        audit(db,dms_tenant,request,"document.evidence.provider_registered",
              "document_evidence_asset",asset_id,
              {"provider_submission_id":submission_id,"sha256":row["sha256"],
               "retention_id":retention_id,"manual_id":manual.id})
        audit(db,dms_tenant,request,"document.retention.created",
              "document_retention_disposition",retention_id,
              {"source_type":"EVIDENCE_ASSET","source_id":asset_id,
               "provider_submission_id":submission_id})
        db.commit()
    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise
    return {"submission_id":submission_id,"dms_evidence_asset_id":asset_id,
            "dms_retention_id":retention_id,"retention_state":retention_state}


@staff_documents_router.get("/submissions/{submission_id}/original")
def staff_original(amo_code:str,submission_id:str,db:Session=Depends(get_db),
                   user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    row=_one(db,"""SELECT object_uri,sha256,filename,content_type
        FROM external_partner_evidence_submissions WHERE amo_id=:amo AND id=:id""",
        amo=amo,id=submission_id)
    if not row:raise HTTPException(404,"Submission unavailable")
    file=storage.materialize(row["object_uri"],expected_sha256=row["sha256"])
    return FileResponse(file,filename=row["filename"],media_type=row["content_type"],
        headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})


@staff_documents_router.get("/submissions/{submission_id}/history")
def history(amo_code:str,submission_id:str,db:Session=Depends(get_db),
            user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    if not _one(db,"""SELECT id FROM external_partner_evidence_submissions
         WHERE amo_id=:amo AND id=:id""",amo=amo,id=submission_id):
        raise HTTPException(404,"Submission unavailable")
    return {"items":_all(db,"""SELECT id,action,details_json,occurred_at,actor_user_id,actor_identity_id
       FROM external_provider_document_events WHERE amo_id=:amo AND submission_id=:id
       ORDER BY occurred_at,id""",amo=amo,id=submission_id)}
