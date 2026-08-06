# Reliability Workbook-Parity Guide

## Status and evidence boundary

The Reliability workbook-parity workspace provides controlled portal registers, lifecycle controls, reviewed workbook imports, statistical-alert snapshots, mapping governance and retained HTML report snapshots. It uses normalized, date-driven records rather than creating one database table or frontend page for each workbook year.

Exact workbook parity is **not yet verified** because the following source files were not available in the repository or connected file library during this implementation review:

- `208B RELIABILITY PROGRAMME(1).xlsm`
- `ANALYSIS TEMPLATE(1).xlsx`
- `DHC8 RELIABILITY PROGRAMME(1).xlsm`

Do not label a workbook profile complete until those files have been inspected directly, including visible and hidden worksheets, formulas, validation lists, protected ranges, charts, macros as reference logic and workbook-specific naming conflicts.

## Portal datasets

The controlled register catalogue includes:

| Code | Portal dataset | Canonical relationship |
| --- | --- | --- |
| AU | Aircraft utilisation | Reliability exposure and utilization records |
| AI | Aircraft incidents | Safety-event evidence |
| FI | Flight interruptions | Technical delay, cancellation, return, turnback, diversion, shutdown and aborted-takeoff events |
| PM | Pilot and maintenance reports | PIREP/MAREP and defect events |
| OOS | Aircraft out of service | Downtime, availability and MTTR evidence |
| RM | Component removals | Scheduled and unscheduled removal events |
| SM | Scheduled maintenance findings | Workpack/task finding evidence |
| SR | Shop reports | Shop finding and no-fault-found events linked to removal/shop references |
| STRUCTURES | Structural damage and repair evidence | Dedicated structural register and defect evidence |
| RECURRING | Recurring defects | Recurrence and FRACAS-linked evidence |
| ECTM | Engine condition and trend monitoring | ECTM/EHM events and snapshots |
| ADD | Deferred defects / MEL / CDL | MEL/CDL deferral events and closure evidence |

FI, SR and ADD use the existing canonical Reliability event types rather than creating competing interruption, shop-finding or deferral domains. Their workbook records retain the original dataset-specific fields, source provenance and derived values.

## Why records are normalized

Workbook tabs often repeat the same structure by month or year. The portal stores the reporting date, aircraft, ATA chapter, lifecycle state and provenance on normalized records. Reports then select approved records by period and profile. This preserves traceability while avoiding duplicated year-specific schemas.

## Local development

From the repository root in PowerShell:

```powershell
git fetch origin
git switch agent/reliability-analytics-dashboard
git pull --ff-only origin agent/reliability-analytics-dashboard

.\.venv\Scripts\Activate.ps1
alembic -c backend/amodb/alembic.ini upgrade heads

cd backend
python run_dev_server.py
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Tenant route format:

```text
http://localhost:5173/maintenance/<AMO_CODE>/reliability
```

Workbook-parity routes:

```text
/maintenance/<AMO_CODE>/reliability/workbook-parity
/maintenance/<AMO_CODE>/reliability/workbook-registers
/maintenance/<AMO_CODE>/reliability/statistical-alerts
/maintenance/<AMO_CODE>/reliability/workbook-mapping
/maintenance/<AMO_CODE>/reliability/workbook-reports
```

The legacy `/workbook-parity` route opens the source-register section. Section changes update the URL so refresh and browser navigation retain the selected workspace.

## Seeding mappings

Use **Mapping & imports** or call:

```text
POST /reliability/workbook-parity/mappings/seed-defaults
GET  /reliability/workbook-parity/mappings
GET  /reliability/workbook-parity/contracts
GET  /reliability/workbook-parity/parity
```

The seed action is idempotent for each tenant/profile/dataset/sheet/column key. C208B, DHC8 and analysis-template mappings are retained separately. The current defaults provide a controlled portal contract and aliases; they are not proof that actual workbook headers and formulas are fully covered until the three source workbooks are inspected.

## Workbook import process

Open **Mapping & imports** and use **Controlled workbook import**.

1. Select the workbook profile and dataset explicitly.
2. Enter the source sheet, or leave it blank only when exactly one controlled sheet alias should match.
3. Enter the header-row number.
4. Select an `.xlsx` or `.xlsm` file of 25 MiB or less.
5. Select **Preview workbook**.
6. Review the detected sheets, header map, source SHA-256 hash, valid rows and row-level errors.
7. Correct the source or mapping when required columns are missing or ambiguous.
8. Commit the next bounded chunk. Each commit processes at most 100 rows from the UI and the backend enforces a maximum of 250.
9. Retry failed rows only after the reported validation or tenant-reference problem is corrected.
10. Open **Source registers** and approve each imported `DRAFT` only after verification.

Security and integrity controls:

- `.xlsx` and `.xlsm` only.
- Extension, MIME type, size and filename checks.
- Path components removed from filenames.
- VBA is not loaded or executed.
- External workbook links are not loaded.
- Formula and formula-error cells are rejected as controlled values.
- Invalid dates, decimals and whole numbers are not silently coerced.
- Ambiguous and duplicate header mappings are rejected.
- Preview is bounded to 10,000 non-empty rows.
- Workbook, sheet, row and SHA-256 provenance are retained.
- Duplicate previews are prevented by tenant/profile/dataset/sheet/source hash.
- Row commits are idempotent by row source hash.
- Imported records remain `DRAFT`; imports never auto-approve canonical Reliability evidence.

Import endpoints:

```text
POST /reliability/workbook-parity/imports/preview
GET  /reliability/workbook-parity/imports
GET  /reliability/workbook-parity/imports/{batch_id}
POST /reliability/workbook-parity/imports/{batch_id}/commit
POST /reliability/workbook-parity/imports/{batch_id}/retry
```

## Creating and approving records

1. Open **Source registers**.
2. Select the dataset.
3. Enter the event date, aircraft, ATA/reference fields and dataset-specific values.
4. Save the record as `DRAFT`.
5. Review source provenance and derived values.
6. Approve the record only after the aircraft, dates, units and required fields are verified.
7. Close an approved record only when closure evidence is available.

Lifecycle:

```text
DRAFT -> APPROVED -> CLOSED
```

Approved records are Reliability evidence. Corrections must use a controlled revision or superseding record; they must not silently overwrite the approved source.

## Statistical alerts

Open **Statistical alerts** and select the source, period, bucket, scope and multipliers. The controlled calculation is:

```text
Warning level = Mean + warning multiplier x sample standard deviation
Alert level   = Mean + alert multiplier x sample standard deviation
```

The implementation uses sample standard deviation. For rates, inspect the retained numerator and denominator evidence. A missing or zero denominator is shown as withheld, not converted to zero.

Charts can remain empty when there are fewer than two usable buckets, no approved source records, no matching aircraft/ATA population, or missing exposure denominators.

## FI rate evidence

FI records can retain:

```text
Dispatch reliability = successful technical dispatches / departures x 100
Schedule completion  = completed departures / scheduled departures x 100
ATA interruption rate = ATA interruptions / flight hours x 100
```

Each calculated value retains its numerator and denominator. When the denominator is absent or zero, the value is withheld with a reason.

## OOS availability and MTTR

OOS metrics require approved records with valid start/end times. Availability also requires scheduled available hours:

```text
Available hours = Scheduled available hours - Downtime hours
Availability %  = Available hours / Scheduled available hours x 100
MTTR             = Completed repair downtime / Completed repair events
```

Availability is withheld when the scheduled-hours denominator is absent or zero.

## Reports and provenance

1. Open **Workbook reports**.
2. Select the retained layout revision.
3. Select the reporting period and aircraft scope.
4. Generate the report.
5. Open the retained HTML preview.
6. Verify the layout code/revision, period, aircraft filter, generation timestamp and SHA-256 hash.

Endpoints:

```text
POST /reliability/workbook-parity/report-layouts/seed
GET  /reliability/workbook-parity/report-layouts
POST /reliability/workbook-parity/reports/render
GET  /reliability/workbook-parity/reports
GET  /reliability/workbook-parity/reports/{id}/html
```

The HTML endpoint is tenant-scoped and authenticated. Raw filesystem report paths are not exposed.

## Roles

The import endpoints require a tenant context and a Reliability data-governance role such as AMO administrator, Quality Manager, Safety Manager or Planning Engineer. Production authorization must also enforce the project permission matrix for:

- viewing registers, calculations and reports;
- creating draft records;
- approving records and mappings;
- closing records with evidence;
- creating report-layout revisions;
- downloading retained reports.

Do not rely on frontend visibility alone as an authorization control.

## Realtime verification

1. Preview a representative workbook and verify sheet/header inventory and row errors.
2. Commit one bounded import chunk and confirm only `DRAFT` records are created.
3. Create a native draft record and confirm it appears only in the active tenant.
4. Approve it and inspect canonical linkage and provenance.
5. Refresh the register and verify status and derived values remain unchanged.
6. Recalculate the relevant metric and inspect numerator/denominator evidence.
7. Generate a report and verify its SHA-256 hash and retained timestamp.
8. Sign in to a different tenant and confirm the batch, record and report are inaccessible.

## Known blockers

The following prevent a complete workbook-parity declaration:

- The three reference workbooks are unavailable for direct inspection.
- Profile-specific zero-gap coverage cannot be confirmed from actual workbook headers, hidden sheets, formulas, validation lists, protection and chart definitions.
- Browser CI uses representative API fixtures rather than a real backend test server and does not yet execute the complete native-entry, approval, alert and report flow against PostgreSQL.
- Canonical AU and ECTM integrations still require removal of remaining floating-point persistence and destructive utilization-update behavior.
- A controlled superseding-record/revision endpoint is still required for approved-record corrections.
- Role-by-role create, approve, close, mapping and report permissions require a complete authorization audit.
- Report layouts have controlled sections and hashes but cannot be described as workbook-equivalent until the source layouts and formulas are inspected and fixture-tested.
