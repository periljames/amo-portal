"""Routes for controlled Reliability workbook reference intake."""
from .workbook_reference_import_core import *

def register(router:APIRouter)->None:
    if not hasattr(legacy,"_batch_dict_original"): legacy._batch_dict_original=legacy._batch_dict
    legacy._batch_dict=batch_dict
    async def read_upload(workbook):
        name=legacy._sanitize_filename(workbook.filename or "workbook.xlsx"); ext=Path(name).suffix.lower()
        if ext not in legacy.ALLOWED_EXTENSIONS: raise HTTPException(415,"Only .xlsx and .xlsm are accepted.")
        content=await workbook.read(legacy.MAX_UPLOAD_BYTES+1)
        if not content: raise HTTPException(422,"Workbook is empty.")
        if len(content)>legacy.MAX_UPLOAD_BYTES: raise HTTPException(413,"Workbook uploads are limited to 25 MiB.")
        return name,ext,content,hashlib.sha256(content).hexdigest()
    @router.post("/workbook-parity/imports/reference-audit")
    async def reference_audit(profile_code:str=Form(...),workbook:UploadFile=File(...),user:accounts.User=Depends(get_current_active_user)):
        legacy._amo_id(user); legacy._require_import_permission(user); name,ext,content,sha=await read_upload(workbook); a=audit(content); match=_profile_match(profile_code,[s["name"] for s in a["sheets"]]); fp=hashlib.sha256(json.dumps({"profile":profile_code,"sheets":[(s["name"],s["state"],s["dimension"]) for s in a["sheets"]]},sort_keys=True).encode()).hexdigest()
        return {"filename":name,"extension":ext,"file_size_bytes":len(content),"source_hash":sha,"structural_fingerprint":fp,"profile_match":match,"integrity":a,"controls":{"vba_execution":"DISABLED","external_links":"NOT_FOLLOWED","formula_results":"NOT_ACCEPTED_AS_CONTROLLED_INPUT","hidden_sheets":"NOT_IMPORTABLE"}}
    @router.post("/workbook-parity/imports/preview",status_code=201)
    async def preview(profile_code:str=Form(...),dataset_code:wp.WorkbookDatasetCode=Form(...),source_sheet:str|None=Form(None),header_row:int=Form(1,ge=1,le=100),workbook:UploadFile=File(...),user:accounts.User=Depends(get_current_active_user),db:Session=Depends(get_write_db)):
        amo=legacy._amo_id(user); legacy._require_import_permission(user)
        if profile_code not in {p["code"] for p in defaults.WORKBOOK_PROFILES}: raise HTTPException(422,"Unknown controlled profile.")
        name,ext,content,sha=await read_upload(workbook); a=audit(content); match=_profile_match(profile_code,[s["name"] for s in a["sheets"]])
        if not match["matched"]: raise HTTPException(422,{"message":"Workbook structure does not match the selected profile.","profile_match":match})
        if profile_code=="GENERIC-ANALYSIS-TEMPLATE": raise HTTPException(422,"The historical analysis workbook is audit-only; import source registers instead.")
        try: book=load_workbook(BytesIO(content),read_only=True,data_only=False,keep_vba=False,keep_links=False)
        except Exception as e: raise HTTPException(422,"Workbook could not be parsed safely.") from e
        definition=wp.DATASET_CATALOG[dataset_code]; expected={norm(n) for n in definition.workbook_sheet_names}; candidates=[n for n in book.sheetnames if norm(n) in expected]
        selected=source_sheet or (candidates[0] if len(candidates)==1 else None)
        if not selected or selected not in book.sheetnames: raise HTTPException(422,{"message":"Sheet detection requires review.","candidate_sheets":candidates})
        sheet=book[selected]
        if sheet.sheet_state!="visible": raise HTTPException(422,"Hidden sheets cannot be imported.")
        if db.query(legacy.ReliabilityWorkbookImportBatch).filter_by(amo_id=amo,profile_code=profile_code,dataset_code=dataset_code.value,selected_sheet=selected,source_hash=sha).one_or_none(): raise HTTPException(409,"This workbook source was already previewed.")
        hr,p1,p2,hmap,herrs=header(sheet,aliases(db,amo,profile_code,dataset_code,selected),header_row); mapped=set(hmap.values())
        if "event_date" not in mapped and dataset_code not in {wp.WorkbookDatasetCode.SB,wp.WorkbookDatasetCode.UR,wp.WorkbookDatasetCode.AS}: herrs.append("A controlled event-date column is required.")
        if not ({"aircraft_serial_number","aircraft_registration","manufacturer_serial_number","registration_number"}&mapped) and dataset_code not in {wp.WorkbookDatasetCode.CS,wp.WorkbookDatasetCode.UR}: herrs.append("Aircraft serial number or registration is required.")
        if herrs: raise HTTPException(422,{"message":"Headers do not satisfy the controlled mapping.","header_errors":herrs,"header_map":hmap,"detected_header_row":hr})
        labels={str(i):str((p2[i-1] if i<=len(p2) else None) or (p1[i-1] if i<=len(p1) else None) or f"Column {i}") for i in range(1,max(len(p1),len(p2))+1)}
        fp=hashlib.sha256(json.dumps({"profile":profile_code,"sheet":selected,"header":hr,"labels":labels},sort_keys=True).encode()).hexdigest(); integrity={**a,"profile_match":match,"selected_sheet":selected,"selected_sheet_state":sheet.sheet_state,"detected_header_row":hr,"structural_fingerprint":fp,"source_hash":sha,"vba_execution":"DISABLED","external_links":"NOT_FOLLOWED","formula_policy":"REJECT_MAPPED_FORMULA_CELLS"}
        detected=[{"name":"__WORKBOOK_INTEGRITY__","state":"metadata","max_row":0,"max_column":0,"integrity":integrity}]+[{"name":s.title,"state":s.sheet_state,"max_row":s.max_row,"max_column":s.max_column} for s in book.worksheets]
        batch=legacy.ReliabilityWorkbookImportBatch(amo_id=amo,profile_code=profile_code,dataset_code=dataset_code.value,original_filename=(workbook.filename or name)[:255],sanitized_filename=name,file_extension=ext,file_size_bytes=len(content),source_hash=sha,status="PREVIEW_READY",detected_sheets=detected,selected_sheet=selected,header_row=hr,header_map=hmap,created_by_user_id=user.id); db.add(batch)
        try: db.flush()
        except IntegrityError as e: db.rollback(); raise HTTPException(409,"This workbook source was already previewed.") from e
        common={"event_date","event_end_date","aircraft_serial_number","aircraft_registration","ata_chapter","reference_code","title","description"}; fields={f.key:f for f in definition.fields}; total=valid=invalid=0
        for rn,cells in enumerate(sheet.iter_rows(min_row=hr+1),start=hr+1):
            if all(c.value in (None,"") for c in cells): continue
            total+=1
            if total>legacy.MAX_PREVIEW_ROWS: db.rollback(); raise HTTPException(422,"Preview is limited to 10,000 non-empty rows.")
            raw={labels.get(str(i),f"Column {i}"):c.value for i,c in enumerate(cells,1) if c.value not in (None,"")}; mapped_values={}; payload={}; errs=[]
            for i,c in enumerate(cells,1):
                key=hmap.get(str(i))
                if not key or c.value in (None,""): continue
                if c.data_type=="f": errs.append(f"{labels.get(str(i),key)} contains a formula; controlled source values must be entered directly."); continue
                try:
                    value=coerce(c.value,fields[key].data_type if key in fields else ("date" if key in {"event_date","event_end_date"} else "text"),labels.get(str(i),key),book.epoch)
                    (mapped_values if key in common else payload)[key]=value
                except (ValueError,InvalidOperation) as e: errs.append(str(e))
            if dataset_code==wp.WorkbookDatasetCode.AS: mapped_values.setdefault("event_date",payload.get("effective_change_date")); mapped_values.setdefault("aircraft_serial_number",payload.get("manufacturer_serial_number")); mapped_values.setdefault("aircraft_registration",payload.get("registration_number"))
            if dataset_code==wp.WorkbookDatasetCode.UR and payload.get("reporting_period"):
                try:mapped_values.setdefault("event_date",coerce(payload["reporting_period"],"date","Reporting period",book.epoch))
                except ValueError as e: errs.append(str(e))
            serial,identity=resolve_aircraft(db,amo,mapped_values.get("aircraft_serial_number"),mapped_values.get("aircraft_registration")); errs+=identity; mapped_values["aircraft_serial_number"]=serial
            if not mapped_values.get("event_date"): errs.append("Event date is required and cannot be inferred.")
            if dataset_code not in {wp.WorkbookDatasetCode.CS,wp.WorkbookDatasetCode.UR} and not serial: errs.append("A tenant aircraft identity is required.")
            for f in definition.fields:
                if f.required and payload.get(f.key) in (None,""): errs.append(f"{f.label} is required.")
            title=str(mapped_values.get("title") or mapped_values.get("reference_code") or payload.get("component_description") or payload.get("item_description") or f"{dataset_code.value} imported row {rn}")[:255]
            record={"dataset_code":dataset_code.value,"event_date":mapped_values.get("event_date"),"event_end_date":mapped_values.get("event_end_date"),"aircraft_serial_number":serial,"ata_chapter":mapped_values.get("ata_chapter"),"reference_code":mapped_values.get("reference_code"),"title":title,"description":mapped_values.get("description"),"payload":payload}; rowsha=hashlib.sha256(json.dumps({"workbook":sha,"sheet":selected,"row":rn,"raw":raw,"mapped":record},sort_keys=True,default=str).encode()).hexdigest(); status="INVALID" if errs else "VALID"; valid+=status=="VALID"; invalid+=status=="INVALID"; db.add(legacy.ReliabilityWorkbookImportRowResult(batch_id=batch.id,row_number=rn,row_source_hash=rowsha,raw_values=raw,mapped_values=record,errors=list(dict.fromkeys(errs)),status=status))
        if not total: db.rollback(); raise HTTPException(422,"Selected sheet contains no operational data rows.")
        batch.total_rows=total; batch.valid_rows=valid; batch.invalid_rows=invalid; db.commit(); db.refresh(batch); rows=db.query(legacy.ReliabilityWorkbookImportRowResult).filter_by(batch_id=batch.id).order_by(legacy.ReliabilityWorkbookImportRowResult.row_number).limit(200).all()
        return {**batch_dict(batch),"preview_rows":[{"id":r.id,"row_number":r.row_number,"status":r.status,"raw_values":r.raw_values,"mapped_values":r.mapped_values,"errors":r.errors,"row_source_hash":r.row_source_hash} for r in rows],"preview_truncated":total>200,"integrity":integrity}
