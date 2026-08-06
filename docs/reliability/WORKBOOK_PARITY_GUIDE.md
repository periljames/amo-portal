# Reliability Workbook-Parity Guide

## Status and evidence boundary

The Reliability workbook-parity workspace provides controlled portal registers, lifecycle controls, statistical-alert snapshots, mapping governance and retained HTML report snapshots. It uses normalized, date-driven records rather than creating one database table or frontend page for each workbook year.

Exact workbook parity is **not yet verified** because the following source files were not available in the repository or connected file library during this implementation review:

- `208B RELIABILITY PROGRAMME(1).xlsm`
- `ANALYSIS TEMPLATE(1).xlsx`
- `DHC8 RELIABILITY PROGRAMME(1).xlsm`

Do not label a workbook profile complete until those files have been inspected directly, including hidden sheets, formulas, validation lists, protected ranges, charts and workbook-specific naming conflicts.

## Portal datasets

The current controlled register catalogue includes:

| Code | Portal dataset |
| --- | --- |
| AU | Aircraft utilisation |
| AI | Aircraft incidents |
| PM | Pilot and maintenance reports |
| OOS | Aircraft out of service |
| RM | Component removals |
| SM | Scheduled maintenance findings |
| STRUCTURES | Structural damage and repair evidence |
| RECURRING | Recurring defects |
| ECTM | Engine condition and trend monitoring |

FI, SR and ADD remain implementation gaps. FI must integrate with canonical interruption events, SR with component removal/shop-visit evidence, and ADD with the controlled MEL/CDL deferral domain rather than creating uncontrolled duplicates.

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

Use the mapping workspace or call:

```text
POST /reliability/workbook-parity/mappings/seed-defaults
GET  /reliability/workbook-parity/mappings
GET  /reliability/workbook-parity/contracts
GET  /reliability/workbook-parity/parity
```

The seed action is intended to be idempotent. Profile completion must be evaluated separately for C208B, DHC8 and the analysis-template family. Current parity aggregation must not be treated as proof of exact workbook coverage until the source workbooks are available and the profile-specific endpoint contract is completed.

## Creating and approving records

1. Open **Workbook registers**.
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

The implementation uses sample standard deviation. For rates, inspect the retained numerator and denominator evidence. A missing or zero denominator must be shown as withheld, not converted to zero.

Charts can remain empty when there are fewer than two usable buckets, no approved source records, no matching aircraft/ATA population, or missing exposure denominators.

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

## Workbook migration process

The required controlled import workflow is not yet complete. Before production workbook migration, implement and verify:

1. Safe `.xlsx`/`.xlsm` upload with size, MIME and extension checks.
2. Macro-disabled parsing.
3. Explicit profile selection or reviewed detection.
4. Sheet/header inventory and ambiguity rejection.
5. Row preview with validation errors.
6. Bounded chunk processing and durable progress.
7. Source-hash idempotency and safe retry.
8. Workbook/sheet/row provenance.
9. Approval before canonical Reliability evidence is created.

Until that workflow exists, use controlled native entry only; do not perform ad hoc bulk inserts.

## Roles

Access must be enforced through tenant permissions:

- Viewers: read registers, calculations and retained reports.
- Reliability data-entry users: create draft records.
- Reliability approvers: approve validated records and mappings.
- Reliability closure authorities: close approved records with evidence.
- Reliability administrators: manage mapping and report-layout revisions.

Confirm the project permission matrix before production use; do not rely on frontend visibility alone.

## Realtime verification

To verify live portal data:

1. Create a draft record and confirm it appears only in the active tenant.
2. Approve it and confirm the canonical linkage/provenance.
3. Refresh the register and verify the status and derived values remain unchanged.
4. Recalculate the relevant metric and inspect numerator/denominator evidence.
5. Generate a report and verify its SHA-256 hash and retained timestamp.
6. Sign in to a different tenant and confirm the record and report are not accessible.

## Known blockers

The following prevent a complete workbook-parity declaration:

- The three reference workbooks are unavailable for direct inspection.
- FI, SR and ADD are absent from the controlled workbook catalogue.
- The workbook upload, preview, chunked import and retry domain is absent.
- Profile-specific parity still requires direct workbook-derived mappings.
- Browser UAT currently uses representative API fixtures rather than a real backend test server.
- Canonical utilization and ECTM integrations must be audited for remaining floating-point persistence and immutable correction behavior.
