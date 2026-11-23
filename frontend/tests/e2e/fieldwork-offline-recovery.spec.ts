import {test,expect,type Page} from '@playwright/test';
import {mockQualityShell} from './helpers/mockQualityShell';
const auditId='11111111-1111-4111-8111-111111111111';
const itemId='22222222-2222-4222-8222-222222222222';
async function prepare(page:Page){
 await mockQualityShell(page);
 await page.route('**/portal-precache.json',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({urls:['/assets/index-next1234.js']})}));
 await page.addInitScript(()=>{
  sessionStorage.setItem('amo_portal_token',`e30.${btoa(JSON.stringify({exp:Math.floor(Date.now()/1000)+3600}))}.fixture`);
  localStorage.setItem('amo_slug','tenant-a');localStorage.setItem('amo_code','AMO-A');localStorage.setItem('amo_department','quality');
  sessionStorage.setItem('amo_onboarding_status',JSON.stringify({is_complete:true,missing:[]}));
  localStorage.setItem('amo_current_user',JSON.stringify({id:'quality',amo_id:'amo-a',amo_slug:'tenant-a',amo_code:'AMO-A',department_code:'quality',role:'QUALITY_MANAGER',full_name:'Quality User',is_active:true}));
 });
 let down=false,commits=0;const keys=new Set<string>();
 const assessment={applicability:'UNVERIFIED',applicability_reason:null,applicability_basis:[],documentary_status:'UNVERIFIED',implementation_status:'UNVERIFIED',field_verification_status:'UNVERIFIED',evidence_ids:[],document_revision_ids:[],regulation_refs:[],procedure_refs:[],conflicts:[],missing_evidence:[],fieldwork_requirements:[]};
 let row={checklist_item_id:itemId,audit_id:auditId,checklist_ref:'1.1',section:'Quality',prompt:'Is the maintenance record controlled?',legacy_response_status:'NOT_VERIFIED',canonical_response_status:'NOT_VERIFIED',response_value:null as string|null,entity_version:0,evidence_references:[],assessment,events:[],auditor_notes:null as string|null};
 const audit={id:auditId,audit_ref:'QAR/TEST/007',title:'Offline fieldwork acceptance',status:'IN_PROGRESS',lead_auditor_user_id:'quality',supporting_auditor_user_ids:[],actual_start:'2026-11-21T08:00:00Z'};
 await page.route('**/api/maintenance/tenant-a/quality/**',async route=>{
  if(route.request().resourceType()==='document')return route.fallback();
  const path=new URL(route.request().url()).pathname;
  const json=(body:unknown,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  if(path.includes('/audits/resolve/'))return json(audit);
  if(path.endsWith('/session'))return json({audit_id:auditId,current_stage_id:'live',current_stage_label:'Live',preparation_issued:true,execution_status:'OPEN',follow_up_status:'OPEN',archive_count:0,fieldwork_access:{ready:true,blocker:null},stages:['setup','prepare','live','closing','follow-up','archive'].map(id=>({id,complete:['setup','prepare'].includes(id),active:id==='live'}))});
  if(path.endsWith('/checklist-execution-governance'))return json({items:[row],canonical_response_values:['COMPLIANT','NONCOMPLIANT','OBSERVATION','NOT_APPLICABLE','NOT_VERIFIED'],legacy_compatibility:{}});
  if(path.endsWith('/checklist-bindings'))return json({items:[{id:'binding-1',audit_id:auditId,template_code:'TEST',revision_no:1,content_sha256:'a'.repeat(64),instantiated_item_ids:[itemId],item_snapshot:[{prompt:row.prompt,response_type:'YES_NO_NA',response_options:[{value:'YES',label:'YES',canonical_status:'COMPLIANT'},{value:'NO',label:'NO',canonical_status:'NONCOMPLIANT'},{value:'NA',label:'N/A',canonical_status:'NOT_APPLICABLE'}],evidence_types:[],evidence_required_when:[],notes_required_when:[]}]}]});
  if(path.endsWith('/findings'))return json([]);
  if(path.endsWith('/fieldwork-mutations')){
   if(down)return route.fulfill({status:503,headers:{'X-AMO-Proxy-Transport-Error':'1'},contentType:'application/json',body:'{"detail":"Request failed"}'});
   const body=route.request().postDataJSON();const key=route.request().headers()['idempotency-key'];
   if(!keys.has(key)){keys.add(key);commits++;row={...row,...body,entity_version:row.entity_version+1};}
   return json({client_mutation_id:body.client_mutation_id,committed_version:row.entity_version,replayed:false,row});
  }
  return json({items:[]});
 });
 return {setDown:(value:boolean)=>{down=value;},commits:()=>commits};
}
async function queued(page:Page){return page.evaluate(async()=>{
 const db=await new Promise<IDBDatabase>((resolve,reject)=>{const req=indexedDB.open('amo-portal-offline',3);req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});
 const rows=await new Promise<any[]>((resolve,reject)=>{const req=db.transaction('outbox').objectStore('outbox').getAll();req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});db.close();return rows.filter(row=>row.entityType==='qms-audit-checklist-item').length;
});}
for(const outage of ['browser offline','server downtime'])test(`fieldwork saves quietly during ${outage} and resumes automatically`,async({page,context})=>{
 const state=await prepare(page);await page.goto(`/maintenance/tenant-a/quality/audits/${auditId}/live`);
 const yes=page.getByRole('radio',{name:/yes.*question 1/i});await expect(yes).toBeEnabled({timeout:20000});
 await expect(page.getByLabel('Portal update available',{exact:true})).toHaveCount(0);
 if(outage==='browser offline')await context.setOffline(true);else state.setDown(true);
 await yes.check();await expect.poll(()=>queued(page),{timeout:15000}).toBe(1);
 await expect(yes).toBeChecked();await expect(page.getByText('Request failed',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('alert').filter({hasText:/Request failed|Checklist update failed/})).toHaveCount(0);
 if(outage==='browser offline')await context.setOffline(false);else state.setDown(false);
 await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
 await expect.poll(()=>state.commits(),{timeout:40000}).toBe(1);await expect.poll(()=>queued(page),{timeout:15000}).toBe(0);
 await expect(yes).toBeChecked();await expect(yes).toBeEnabled();
 await page.getByRole('textbox',{name:/Remarks for question 1/}).fill('Continued editing after automatic server recovery.');
 await page.getByRole('button',{name:'Save remarks',exact:true}).click();await expect.poll(()=>state.commits(),{timeout:15000}).toBe(2);
 await expect(page.getByRole('alert').filter({hasText:/Request failed|Checklist update failed/})).toHaveCount(0);
});

test('a parked NO draft does not prevent changing back to YES, and its text is retained',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const state=await prepare(page);await page.goto(`/maintenance/tenant-a/quality/audits/${auditId}/live`);
 const yes=page.getByRole('radio',{name:/yes.*question 1/i});const no=page.getByRole('radio',{name:/no.*question 1/i});
 await expect(yes).toBeEnabled({timeout:20000});await yes.check();await expect.poll(()=>state.commits()).toBe(1);
 await no.check();await page.getByRole('textbox',{name:'Finding statement',exact:true}).fill('Retained finding notes while checking the assessment.');await page.getByRole('button',{name:'Save draft and close finding composer'}).click();await expect(no).toBeChecked();
 await yes.check();await expect.poll(()=>state.commits()).toBe(2);await expect(yes).toBeChecked();await expect(no).not.toBeChecked();
 await no.check();await expect(page.getByRole('textbox',{name:'Finding statement',exact:true})).toHaveValue('Retained finding notes while checking the assessment.');await expect(page.getByRole('button',{name:'Save draft and close finding composer'})).toBeVisible();
 await page.getByRole('button',{name:'Save draft and close finding composer'}).click();
 expect(errors).toEqual([]);
});

async function evidenceRows(page:Page){return page.evaluate(async()=>{
 const db=await new Promise<IDBDatabase>((resolve,reject)=>{const r=indexedDB.open('amo-qms-offline-evidence',2);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
 const rows=await new Promise<any[]>((resolve,reject)=>{const r=db.transaction('evidence').objectStore('evidence').getAll();r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});db.close();return rows.map(r=>({filename:r.filename,size:r.sizeBytes,type:r.contentType,encrypted:r.fileCiphertext.byteLength>0}));
});}

test('desktop camera captures an actual JPEG offline and stops the camera',async({page,context})=>{
 await prepare(page);await page.addInitScript(()=>{
  Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async()=>{
   const canvas=document.createElement('canvas');canvas.width=320;canvas.height=240;
   const draw=()=>{const c=canvas.getContext('2d')!;c.fillStyle='#126fa8';c.fillRect(0,0,320,240);};draw();
   const timer=setInterval(draw,40);const stream=canvas.captureStream(15);
   (window as any).cameraTracks=stream.getTracks();stream.getTracks().forEach(t=>t.addEventListener('ended',()=>clearInterval(timer)));return stream;
  }});
 });
 await page.goto(`/maintenance/tenant-a/quality/audits/${auditId}/live`);await expect(page.getByRole('radio',{name:/yes.*question 1/i})).toBeEnabled({timeout:20000});
 await context.setOffline(true);await page.getByLabel('Attach evidence for 1.1',{exact:true}).click();await page.getByRole('button',{name:'Take photo',exact:true}).click();
 const camera=page.getByRole('dialog',{name:'Camera capture'});await expect(camera).toBeVisible();await expect(camera.getByRole('button',{name:'Capture photo',exact:true})).toBeEnabled();
 await page.screenshot({path:'../.artifacts/fieldwork-camera-preview.png'});await camera.getByRole('button',{name:'Capture photo',exact:true}).click();await expect(camera).toHaveCount(0);
 await expect.poll(async()=> (await evidenceRows(page)).length).toBe(1);const rows=await evidenceRows(page);expect(rows[0].type).toBe('image/jpeg');expect(rows[0].size).toBeGreaterThan(500);expect(rows[0].encrypted).toBe(true);
 expect(await page.evaluate(()=>(window as any).cameraTracks.every((t:MediaStreamTrack)=>t.readyState==='ended'))).toBe(true);
 await expect(page.getByText(/saved on this device/).first()).toBeVisible();
});

test('phone capture uses the native rear camera and saves the chosen photo offline',async({page,context})=>{
 await prepare(page);await page.setViewportSize({width:390,height:844});await page.addInitScript(()=>Object.defineProperty(navigator,'userAgent',{configurable:true,get:()=> 'Mozilla/5.0 Android Mobile'}));
 await page.goto(`/maintenance/tenant-a/quality/audits/${auditId}/live`);await expect(page.getByRole('radio',{name:/yes.*question 1/i})).toBeEnabled({timeout:20000});
 await context.setOffline(true);await page.getByLabel('Attach evidence for 1.1',{exact:true}).click();const chooser=page.waitForEvent('filechooser');await page.getByRole('button',{name:'Take photo',exact:true}).click();
 const picker=await chooser;expect(await picker.element().getAttribute('capture')).toBe('environment');
 await picker.setFiles({name:'phone.jpg',mimeType:'image/jpeg',buffer:Buffer.from('phone camera fixture')});await expect.poll(async()=> (await evidenceRows(page)).length).toBe(1);
 await expect(page.getByText('phone.jpg saved on this device',{exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);await page.screenshot({path:'../.artifacts/fieldwork-phone-evidence.png'});
});

test('camera permission denial offers a working file upload fallback',async({page,context})=>{
 await prepare(page);await page.addInitScript(()=>Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async()=>{throw new DOMException('Camera permission denied','NotAllowedError');}}));
 await page.goto(`/maintenance/tenant-a/quality/audits/${auditId}/live`);await expect(page.getByRole('radio',{name:/yes.*question 1/i})).toBeEnabled({timeout:20000});
 await context.setOffline(true);await page.getByLabel('Attach evidence for 1.1',{exact:true}).click();await page.getByRole('button',{name:'Take photo',exact:true}).click();
 const camera=page.getByRole('dialog',{name:'Camera capture'});await expect(camera).toContainText('Camera permission denied');const chooser=page.waitForEvent('filechooser');await camera.getByRole('button',{name:'Upload files instead',exact:true}).click();
 await (await chooser).setFiles([{name:'record.txt',mimeType:'text/plain',buffer:Buffer.from('record')},{name:'evidence.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF evidence')}]);
 await expect.poll(async()=> (await evidenceRows(page)).length).toBe(2);await expect(camera).toHaveCount(0);
});


test('N/A draft can be changed back to YES without a reload or lost remarks',async({page,context})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await prepare(page);await page.goto(`/maintenance/tenant-a/quality/audits/${auditId}/live`);
 const yes=page.getByRole('radio',{name:/yes.*question 1/i});await expect(yes).toBeEnabled({timeout:20000});await context.setOffline(true);
 await yes.check();await expect.poll(()=>queued(page)).toBe(1);
 const remarks=page.getByRole('textbox',{name:/Remarks for question 1/});await remarks.fill('Evidence retained while changing an assessment.');
 const na=page.getByRole('radio',{name:/n\/a.*question 1/i});await na.check();await expect(na).toBeChecked();await expect(page.getByRole('button',{name:'Save remarks',exact:true})).toBeEnabled();
 await yes.check();await expect(yes).toBeChecked();await expect(na).not.toBeChecked();await expect(remarks).toHaveValue('Evidence retained while changing an assessment.');expect(errors).toEqual([]);
});


test('repeated answer changes and fast finding typing stay stable',async({page})=>{
 test.setTimeout(120_000);
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));const state=await prepare(page);
 await page.goto(`/maintenance/tenant-a/quality/audits/${auditId}/live`);
 const yes=page.getByRole('radio',{name:/yes.*question 1/i});const no=page.getByRole('radio',{name:/no.*question 1/i});await expect(yes).toBeEnabled({timeout:20000});
 for(let i=0;i<8;i++){
  await no.check();const statement=page.getByRole('textbox',{name:'Finding statement',exact:true});await statement.fill(`Finding draft cycle ${i}. `);await statement.pressSequentially('Typing remains responsive while the checklist stays mounted.');
  await page.getByRole('button',{name:'Save draft and close finding composer'}).click();await yes.check();await expect.poll(()=>state.commits()).toBe(i+1);await expect(yes).toBeChecked();
 }
 await no.check();await page.getByRole('button',{name:'Discard draft',exact:true}).click();await expect(yes).toBeChecked();await expect(page.getByLabel('Saved finding drafts')).toHaveCount(0);expect(errors).toEqual([]);
 await page.screenshot({path:'../.artifacts/fieldwork-checklist-verified.png'});
});


test('closing a pending camera request stops its eventual stream',async({page})=>{
 await prepare(page);await page.addInitScript(()=>Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:()=>new Promise<MediaStream>(resolve=>{
  (window as any).finishCameraRequest=()=>{const canvas=document.createElement('canvas');canvas.width=320;canvas.height=240;const stream=canvas.captureStream();(window as any).cancelledTracks=stream.getTracks();resolve(stream);};
 })}));
 await page.goto(`/maintenance/tenant-a/quality/audits/${auditId}/live`);await expect(page.getByRole('radio',{name:/yes.*question 1/i})).toBeEnabled({timeout:20000});
 await page.getByLabel('Attach evidence for 1.1',{exact:true}).click();await page.getByRole('button',{name:'Take photo',exact:true}).click();
 const modal=page.getByRole('dialog',{name:'Camera capture'});await expect(modal.getByRole('button',{name:'Capture photo',exact:true})).toBeDisabled();await modal.getByRole('button',{name:'Close camera'}).click();
 await page.evaluate(()=>(window as any).finishCameraRequest());await expect.poll(()=>page.evaluate(()=>(window as any).cancelledTracks.every((t:MediaStreamTrack)=>t.readyState==='ended'))).toBe(true);await expect(modal).toHaveCount(0);
});

test('QR phone handoff attaches original files and updates the desktop without phone login',async({page,browser})=>{
 page.on('pageerror',e=>console.log('PHONE PAGE ERROR',e.message));page.on('console',m=>{if(m.type()==='error')console.log('PHONE CONSOLE',m.text());});
 const state=await prepare(page);void state;const photos:any[]=[];
 await page.route('**/phone-capture',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({token:'synthetic-phone-only-token',expires_at:new Date(Date.now()+600000).toISOString()})}));
 await page.route('**/audits/*/evidence?*',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({items:photos})}));
 await page.goto(`/maintenance/tenant-a/quality/audits/${auditId}/live`);await expect(page.getByRole('radio',{name:/yes.*question 1/i})).toBeEnabled({timeout:60000});
 await page.getByLabel('Attach evidence for 1.1',{exact:true}).click();await page.getByRole('button',{name:'Use phone camera',exact:true}).click();
 const handoff=page.getByRole('dialog',{name:'Use phone camera'});await expect(handoff.getByRole('img',{name:'QR code for phone camera'})).toBeVisible({timeout:20000});const url=await handoff.getByRole('link',{name:'Open phone capture page'}).getAttribute('href');expect(url).toContain('#synthetic-phone-only-token');await page.screenshot({path:'../.artifacts/phone-handoff-qr.png'});
 const phoneContext=await browser.newContext({viewport:{width:390,height:844},serviceWorkers:'block'});const phone=await phoneContext.newPage();await mockQualityShell(phone);
 let attempts=0;const ids:string[]=[];const original=Buffer.from(await page.evaluate(()=>{const canvas=document.createElement('canvas');canvas.width=4032;canvas.height=3024;const c=canvas.getContext('2d')!;c.fillStyle='#126fa8';c.fillRect(0,0,canvas.width,canvas.height);return canvas.toDataURL('image/jpeg',0.95).split(',')[1];}),'base64');
 await phone.route('**/quality/audit-access/phone-capture',async route=>{
  expect(route.request().headers()['x-phone-capture']).toBe('synthetic-phone-only-token');
  if(route.request().method()==='GET')return route.fulfill({contentType:'application/json',body:JSON.stringify({question:'Is the maintenance record controlled?',checklist_ref:'1.1',expires_at:Math.floor(Date.now()/1000)+600})});
  attempts++;const bytes=route.request().postDataBuffer()!;expect(bytes.includes(original)).toBe(true);const text=bytes.toString();ids.push(text.match(/name="capture_id"\r\n\r\n([^\r]+)/)![1]);
  if(attempts===1)return route.fulfill({status:503,contentType:'application/json',body:'{"detail":"Temporarily unavailable. Retry photo."}'});
  photos.push({id:'phone-photo-1',audit_id:auditId,checklist_item_id:itemId,finding_id:null,source_type:'INTERNAL_USER',filename:'full-resolution.jpg',content_type:'image/jpeg',size_bytes:original.length,sha256:'a'.repeat(64),description:null,context:{},source_device_id:'paired-phone',created_at:new Date().toISOString()});return route.fulfill({contentType:'application/json',body:JSON.stringify({artifact:photos[0],committed_version:1,replayed:false})});
 });
 await phone.goto(url!);await expect(phone.getByRole('heading',{name:'Capture photos'})).toBeVisible();await expect(phone.getByRole('button',{name:'Take photo',exact:true})).toBeEnabled();
 const chooser=phone.waitForEvent('filechooser');await phone.getByRole('button',{name:'Take photo',exact:true}).click();const picker=await chooser;expect(await picker.element().getAttribute('capture')).toBe('environment');await picker.setFiles({name:'full-resolution.jpg',mimeType:'image/jpeg',buffer:original});
 await phone.getByRole('button',{name:'Attach photos to checklist'}).click();await expect(phone.getByText('Ready to retry',{exact:false})).toBeVisible();await phone.getByRole('button',{name:'Attach photos to checklist'}).click();await expect(phone.getByText('Photos attached. You can continue on your computer or take more photos.')).toBeVisible();
 await expect(phone.getByText('Upload failed',{exact:true})).toHaveCount(0);expect(ids[0]).toBe(ids[1]);expect(await phone.evaluate(()=>sessionStorage.getItem('amo_portal_token'))).toBeNull();await expect(handoff).toContainText('1 photo received');await phone.screenshot({path:'../.artifacts/phone-handoff-mobile.png'});expect(await phone.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);await phoneContext.close();
});

test('an expired phone link does not log an already signed-in user out',async({page})=>{
 await prepare(page);let refreshes=0;
 await page.route('**/auth/refresh',route=>{refreshes++;return route.fulfill({status:401,contentType:'application/json',body:'{}'});});
 await page.route('**/quality/audit-access/phone-capture',route=>route.fulfill({status:401,contentType:'application/json',body:'{"detail":"Phone capture link has expired. Generate a new QR code."}'}));
 await page.goto('/qms/phone-capture#expired-capture-link');await expect(page.getByRole('alert').filter({hasText:'Phone capture link has expired.'})).toBeVisible();expect(await page.evaluate(()=>sessionStorage.getItem('amo_portal_token'))).toBeTruthy();expect(refreshes).toBe(0);expect(new URL(page.url()).pathname).toBe('/qms/phone-capture');
});
test('phone fieldwork keeps navigation and filters out of the working area',async({page})=>{
 await page.setViewportSize({width:390,height:844});await prepare(page);await page.goto(`/maintenance/tenant-a/quality/audits/${auditId}/live`);await expect(page.getByRole('radio',{name:/yes.*question 1/i})).toBeEnabled({timeout:20000});
 const data=await page.evaluate(async({auditId})=>(await fetch(`/api/maintenance/tenant-a/quality/audits/${auditId}/checklist-execution-governance`)).json(),{auditId});
 const rows=Array.from({length:8},(_,i)=>({...data.items[0],checklist_item_id:`22222222-2222-4222-8222-${String(i+1).padStart(12,'0')}`,checklist_ref:`1.${i+1}`,prompt:`Is maintenance record ${i+1} controlled?`}));
 await page.route('**/checklist-bindings',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({items:[{id:'mobile',audit_id:auditId,content_sha256:'a'.repeat(64),template_code:'TEST',revision_no:1,instantiated_item_ids:rows.map(row=>row.checklist_item_id),item_snapshot:rows.map(row=>({prompt:row.prompt,response_type:'YES_NO_NA',response_options:[{value:'YES',label:'YES',canonical_status:'COMPLIANT'},{value:'NO',label:'NO',canonical_status:'NONCOMPLIANT'},{value:'NA',label:'N/A',canonical_status:'NOT_APPLICABLE'}]}))}]})}));
 await page.route('**/checklist-execution-governance',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({...data,items:rows})}));await page.reload();await expect(page.getByRole('radio',{name:/yes.*question 1.1/i})).toBeEnabled();
 await expect(page.locator('.quality-context-bar-host')).toBeHidden();await expect(page.locator('.audit-fieldwork-header .theme-toggle-btn')).toHaveCount(0);await expect(page.getByLabel('Filter checklist',{exact:true})).toBeHidden();
 await page.screenshot({path:'../.artifacts/qms-remodel-fieldwork-top.png'});const questions=page.locator('.audit-checklist-table__question');await expect(questions).toHaveCount(8);expect(await questions.nth(0).evaluate(e=>e.getBoundingClientRect().top)).toBeLessThan(320);
 expect(await page.locator('.audit-checklist-table-scroll').evaluate(e=>getComputedStyle(e).overflow)).toBe('visible');
 await page.getByRole('button',{name:'Checklist filters',exact:true}).click();await expect(page.getByLabel('Filter checklist',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Checklist filters',exact:true}).click();await expect(page.getByLabel('Filter checklist',{exact:true})).toBeHidden();
 await page.screenshot({path:'../.artifacts/qms-remodel-fieldwork-top.png'});await page.getByRole('button',{name:'Open navigation',exact:true}).click();await expect(page.locator('.tenant-shell__sidebar')).toHaveAttribute('aria-hidden','false');await expect(page.locator('.tenant-shell__sidebar .tenant-nav')).toBeVisible();await page.keyboard.press('Escape');await expect(page.locator('.tenant-shell__sidebar')).toHaveAttribute('aria-hidden','true');
 await questions.nth(7).scrollIntoViewIfNeeded();await expect(questions.nth(7)).toBeVisible();await page.screenshot({path:'../.artifacts/qms-remodel-fieldwork-phone.png'});
});

test('a phone photo can be removed offline and replaced without changing the answer',async({page,context})=>{
 await prepare(page);await page.setViewportSize({width:390,height:844});await page.goto(`/maintenance/tenant-a/quality/audits/${auditId}/live`);await expect(page.getByRole('radio',{name:/yes.*question 1/i})).toBeEnabled({timeout:20000});await context.setOffline(true);
 await page.getByLabel('Attach evidence for 1.1',{exact:true}).click();await page.getByLabel('Upload question evidence',{exact:true}).setInputFiles({name:'retake.jpg',mimeType:'image/jpeg',buffer:Buffer.from('test photo')});await expect.poll(async()=>(await evidenceRows(page)).length).toBe(1);
 await page.getByRole('button',{name:'Remove retake.jpg',exact:true}).click();await expect.poll(async()=>(await evidenceRows(page)).length).toBe(0);
 await page.getByLabel('Upload question evidence',{exact:true}).setInputFiles({name:'replacement.jpg',mimeType:'image/jpeg',buffer:Buffer.from('new photo')});await expect.poll(async()=>(await evidenceRows(page)).length).toBe(1);await expect(page.getByRole('button',{name:'Remove replacement.jpg',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Retry replacement.jpg',exact:true}).click();await expect(page.getByText('Upload queued for retry',{exact:true})).toBeVisible();expect((await evidenceRows(page))[0].filename).toBe('replacement.jpg');
});

test('an uploaded photo exposes removal and refreshes the checklist version',async({page})=>{
 await prepare(page);let removed=false,version:number|undefined;
 const artifact={id:'saved-photo',audit_id:auditId,sha256:'a'.repeat(64),filename:'saved.jpg',uploaded_by_user_id:'quality',size_bytes:1024,context:{},source_type:'INTERNAL_USER'};
 await page.route(`**/audits/${auditId}/evidence**`,r=>{if(r.request().method()==='DELETE'){removed=true;version=Number(new URL(r.request().url()).searchParams.get('base_version'));return r.fulfill({contentType:'application/json',body:'{"removed":true,"committed_version":1}'});}return r.fulfill({contentType:'application/json',body:JSON.stringify({items:removed?[]:[artifact]})});});
 await page.goto(`/maintenance/tenant-a/quality/audits/${auditId}/live`);await expect(page.getByRole('radio',{name:/yes.*question 1/i})).toBeEnabled({timeout:20000});await page.getByLabel('Attach evidence for 1.1',{exact:true}).click();await page.getByRole('button',{name:'Remove saved.jpg',exact:true}).click();await expect.poll(()=>removed).toBe(true);expect(version).toBe(0);await expect(page.getByRole('button',{name:'Remove saved.jpg',exact:true})).toHaveCount(0);
});
