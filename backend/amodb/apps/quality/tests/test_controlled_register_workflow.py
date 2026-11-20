from dataclasses import replace

from amodb.apps.quality import controlled_register_router as registers
from amodb.apps.quality import management_review_router as review
from amodb.apps.quality.tests.test_management_review_workflow import client  # noqa: F401


def risk_body():
    return {"title": "Assessment of supplier continuity", "description": "Potential service disruption", "status": "OPEN", "owner_user_id": "chair", "due_date": "2026-11-30", "fields": {
        "likelihood": 3, "consequence": 4, "rating": "HIGH", "existing_controls": "Approved alternate provider", "assessment_basis": "Assessed against current operational exposure"}}


def test_risk_matrix_record_editing_and_tenant_isolation(client):
    root = "/register-workspace/risk/register"
    r = client.post(root, json=risk_body())
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["payload"]["risk_score"] == 12
    data = client.get("/register-workspace/risk/risk-matrix").json()
    assert data["risk_matrix"][2][3] == 1
    assert data["unassessed"] == 0
    r = client.put(f"{root}/{row['id']}", json={**risk_body(), "title": "Updated risk assessment", "expected_version": row["version"]})
    assert r.status_code == 200, r.text
    history = client.get("/register-workspace/risk/trends").json()["risk_history"]
    assert len(history) == 2
    assert history[0]["assessment"]["risk_score"] == 12
    assert "Recorded at,Risk,Status,Assessor ID" in client.get("/register-workspace/risk/trends/export").text
    assert client.put(f"{root}/{row['id']}", json={**risk_body(), "expected_version": row["version"]}).status_code == 409
    client.app.dependency_overrides[review.resolve_tenant_context] = lambda: replace(client.ctx, amo_id="tenant-b", user_id="outsider")
    assert client.get(root).json()["total"] == 0
    assert client.get(f"{root}/{row['id']}").status_code == 404


def test_required_risk_fields_scope_source_and_unknown_views(client):
    body = risk_body()
    for likelihood in (0, 6, "3.5", "not a number"):
        r = client.post("/register-workspace/risk/register", json={**body, "fields": {**body["fields"], "likelihood": likelihood}})
        assert r.status_code == 422
    assert client.post("/register-workspace/risk/register", json={**body, "fields": {**body["fields"], "unknown": "bad"}}).status_code == 422
    assert client.get("/register-workspace/risk/not-a-view").status_code == 404
    scope = {"title": "Maintenance organization QMS scope", "status": "OPEN", "owner_user_id": "chair", "fields": {"boundaries": "Approved maintenance activities and organizational locations", "applicability": "Processes under the organization's approved scope"}}
    r = client.post("/register-workspace/system/qms-scope", json=scope)
    assert r.status_code == 201, r.text
    assert client.get("/register-workspace/system/qms-scope").json()["items"][0]["title"] == scope["title"]
    assert client.get("/register-workspace/system/processes").json()["total"] == 0


def test_calibration_failure_preserves_evidence_and_controls_serviceability(client):
    root = "/register-workspace/equipment-calibration"
    body = {"title": "Torque wrench", "status": "ACTIVE", "owner_user_id": "chair", "due_date": "2026-11-30", "fields": {"asset_reference": "TOOL-001", "serial_number": "SN-1", "calibration_basis": "Approved interval and procedure"}}
    response = client.post(root + "/register", json=body)
    assert response.status_code == 201, response.text
    equipment = response.json()
    calibration = {"title": "Torque wrench calibration", "status": "COMPLETE", "owner_user_id": "chair", "due_date": "2027-11-18", "fields": {"equipment_id": equipment["id"], "performed_on": "2026-11-18", "certificate_reference": "CERT-1", "result": "FAIL", "laboratory": "Approved laboratory", "completion_evidence": "Certificate retained; result outside approved tolerance"}}
    response = client.post(root + "/calibration-history", json=calibration)
    assert response.status_code == 201, response.text
    cal = response.json()
    equipment = client.get(root + "/register/" + equipment["id"]).json()
    assert equipment["status"] == "OUT_OF_SERVICE"
    assert equipment["due_date"] == "2027-11-18"
    report = client.get(root + "/reports").json()["equipment_report"]
    assert report["equipment_total"] == 1 and report["out_of_service"] == 1
    assert report["retained_calibrations"] == 1 and report["failed"] == 1 and report["passed"] == 0
    export = client.get(root + "/reports/export")
    assert "Out of service,1" in export.text and "Passed,0" in export.text
    assert "Torque wrench calibration" in export.text
    assert client.put(root + "/calibration-history/" + cal["id"], json={**calibration, "expected_version": cal["version"]}).status_code == 409
    r = client.put(root + "/register/" + equipment["id"], json={**body, "expected_version": equipment["version"]})
    assert r.status_code == 422
    r = client.put(root + "/register/" + equipment["id"], json={**body, "expected_version": equipment["version"], "fields": {**body["fields"], "serviceability_basis": "Repaired and independently verified against retained certificate"}})
    assert r.status_code == 200, r.text


def test_open_tolerance_event_blocks_return_to_service_even_with_evidence(client):
    root = "/register-workspace/equipment-calibration"
    equipment_body = {"title": "Pressure gauge", "status": "ACTIVE", "owner_user_id": "chair", "due_date": "2027-01-01", "fields": {"asset_reference": "TOOL-002", "serial_number": "SN-2", "calibration_basis": "Approved procedure"}}
    equipment = client.post(root + "/register", json=equipment_body).json()
    event_body = {"title": "Pressure gauge outside tolerance", "status": "OPEN", "owner_user_id": "chair", "due_date": "2026-12-01", "fields": {"equipment_id": equipment["id"], "discovered_on": "2026-11-18", "impact": "Affected work under review", "containment": "Gauge isolated"}}
    response = client.post(root + "/out-of-tolerance", json=event_body)
    assert response.status_code == 201, response.text
    event = response.json()
    equipment = client.get(root + "/register/" + equipment["id"]).json()
    return_body = {**equipment_body, "expected_version": equipment["version"], "fields": {**equipment_body["fields"], "serviceability_basis": "Repair and calibration certificate retained"}}
    assert client.put(root + "/register/" + equipment["id"], json=return_body).status_code == 422
    assert client.get(root + "/reports").json()["equipment_report"]["open_tolerance_cases"] == 1
    response = client.put(root + "/out-of-tolerance/" + event["id"], json={**event_body, "status": "CLOSED", "expected_version": event["version"], "fields": {**event_body["fields"], "completion_evidence": "Impact assessed and disposition approved"}})
    assert response.status_code == 200, response.text
    response = client.put(root + "/register/" + equipment["id"], json=return_body)
    assert response.status_code == 200, response.text


def test_external_closeout_evidence_and_full_csv_formula_safety(client):
    root = "/register-workspace/external-interface/customer-complaints"
    body = {"title": "=External case", "status": "CLOSED", "owner_user_id": "chair", "fields": {"external_reference": "CASE-1", "party": "Customer", "received_on": "2026-11-18", "category": "SERVICE", "impact": "Reported service disruption requiring controlled closure."}}
    assert client.post(root, json=body).status_code == 422
    body["fields"]["completion_evidence"] = "Agreed response and resolution retained with case"
    response = client.post(root, json=body)
    assert response.status_code == 201, response.text
    export = client.get(root + "/export")
    assert export.status_code == 200
    assert "'=External case" in export.text
    assert "qms.reports.export" in client.permissions
    assert "qms.external.manage" in client.permissions


def test_calibration_report_keeps_legacy_missing_dates_and_results_unclassified(client):
    from sqlalchemy import text
    client.connection.execute(text("INSERT INTO qms_equipment (id,amo_id,title,status) VALUES ('legacy','tenant-a','Legacy gauge','ACTIVE'),('foreign','tenant-b','Foreign gauge','ACTIVE')"))
    client.connection.execute(text("INSERT INTO qms_calibration_records (id,amo_id,title,status) VALUES ('legacy-result','tenant-a','Legacy retained result','COMPLETE')"))
    client.connection.commit()
    response = client.get("/register-workspace/equipment-calibration/reports")
    assert response.status_code == 200, response.text
    report = response.json()["equipment_report"]
    assert report["equipment_total"] == 1 and report["active"] == 1
    assert report["active_missing_due_date"] == 1
    assert report["active_within_due_date"] == 0 and report["active_overdue"] == 0
    assert report["retained_calibrations"] == 1 and report["passed"] == 0 and report["failed"] == 0


def test_completed_calibration_cannot_be_dated_in_the_future(client):
    from datetime import date, timedelta
    root = "/register-workspace/equipment-calibration"
    due = (date.today() + timedelta(days=365)).isoformat()
    response = client.post(root + "/register", json={"title": "Date validation gauge", "status": "ACTIVE", "owner_user_id": "chair", "due_date": due, "fields": {"asset_reference": "DATE-001", "serial_number": "D-1", "calibration_basis": "Approved interval"}})
    assert response.status_code == 201, response.text
    equipment = response.json()
    body = {"title": "Future completed calibration", "status": "COMPLETE", "owner_user_id": "chair", "due_date": due, "fields": {"equipment_id": equipment["id"], "performed_on": (date.today() + timedelta(days=1)).isoformat(), "certificate_reference": "FUTURE-001", "result": "PASS", "laboratory": "Laboratory", "completion_evidence": "Synthetic date-validation fixture"}}
    response = client.post(root + "/calibration-history", json=body)
    assert response.status_code == 422, response.text
    assert client.get(root + "/calibration-history").json()["total"] == 0
    assert client.get(root + "/register/" + equipment["id"]).json()["version"] == equipment["version"]
