# Reliability Workbook Reference Audit

Date: 2026-08-07

This document records the portal-side workbook controls and the remaining evidence required before workbook parity can be certified. The portal database, controlled source registers, approved calculation snapshots, and retained reports are authoritative operational records.

## Verification status

The following source workbooks are required for final parity acceptance:

- `208B RELIABILITY PROGRAMME(1).xlsm`
- `ANALYSIS TEMPLATE(1).xlsx`
- `DHC8 RELIABILITY PROGRAMME(1).xlsm`

Those source files are not currently retained in this repository and are not available to the present verification run. Therefore this PR does **not** claim independently verified source SHA-256 values, workbook sizes, hidden-sheet counts, formula counts, chart counts, formula-error counts, external-link counts, VBA signatures, or exact report-layout equivalence.

Any structural values recorded during an earlier exploratory inspection must be regenerated from the original workbook bytes before they can be used as controlled acceptance evidence. The `/workbook-parity/imports/reference-audit` endpoint performs that audit from the uploaded bytes and returns the source hash, structural fingerprint, sheet states, formulas, cached errors, charts, external links, and VBA indicators without executing VBA or following links.

## Controlled source domains

The portal catalogue covers the governed Reliability domains:

`AU`, `AI`, `FI`, `PM`, `OOS`, `RM`, `SM`, `SR`, `SB`, `CS`, `AS`, `UR`, `STRUCTURES`, `RECURRING`, `ECTM`, and `ADD`.

The DHC8-oriented `SB`, `CS`, `AS`, and component `UR`/`MTBUR` contracts are represented. Aircraft registration and manufacturer serial number remain distinct identities and are resolved against the tenant fleet before an import row can be queued.

The C208B and DHC8 profile definitions include required-sheet contracts used to reject obviously mismatched workbooks. These are application contracts, not a substitute for direct comparison with the original source files.

## Analytical methods

### Exact sample-sigma method

The portal uses fixed-point `Decimal` arithmetic:

- Mean: `Σx / n`
- Sample standard deviation: `sqrt(Σ(x - mean)^2 / (n - 1))`
- Warning: `mean + warning_multiplier × sample_standard_deviation`
- Alert: `mean + alert_multiplier × sample_standard_deviation`

At least three valid periods are required. Missing periods are not silently replaced with zero.

### Workbook-reference method

A separately labelled 12-period compatibility method is implemented for continuity with the intended workbook workflow:

- Population sigma over the latest 12 consecutive periods.
- Population sigma of the 11 adjacent two-period means.
- Warning: `mean + moving_mean_sigma + 2 × population_sigma`.
- Alert: `mean + moving_mean_sigma + 3 × population_sigma`.

This method is not represented as statistically preferred. Exact equivalence to the original workbooks remains **unverified until the source files are re-audited and fixture comparisons pass**.

### Variable-exposure event rates

For rates based on flight hours or flight cycles, the portal supports a Poisson u-chart:

- Centre: `Σevents / Σexposure × scale`.
- Period sigma: `sqrt(centre × scale / period_exposure)`.
- Each period retains its own warning and alert limits.
- The default scale is 1,000.
- A legacy per-100-flight-hour route remains available only for compatibility.

### Component removal analysis

The component analysis is represented with exact calculations:

- Exposure unit-hours: `quantity_per_aircraft × fleet_unit_hours`.
- URR per 1,000 unit-hours: `unscheduled_removals / exposure × 1,000`.
- MTBUR: `exposure / unscheduled_removals`.
- Total removal rate per 1,000 unit-hours: `total_removals / exposure × 1,000`.
- MTBR: `exposure / total_removals`.

Zero-removal periods produce an explicit no-event status and a withheld MTBUR/MTBR value instead of a divide-by-zero result.

## Tamper-resistance controls

- Fixed-point database storage for controlled Reliability analytical values covered by the migrations and schema gates.
- Source workbook SHA-256, structural fingerprint, selected-sheet state, header row, and row SHA-256 evidence are generated from uploaded source bytes.
- Profile-specific required-sheet matching for the C208B and DHC8 profiles.
- Hidden sheets are not importable.
- Formula cells are rejected when mapped to controlled input fields.
- VBA is never executed and external links are not followed during controlled intake.
- The historical analysis template is audit-only and cannot be committed as operational source evidence.
- Imported evidence is created only as `DRAFT` and requires a separate approval action.
- Approved and closed workbook records are database-immutable.
- Statistical results and retained report snapshots are append-only at database level.
- Completed import batches and their row evidence are immutable at database level.
- Governed statistical results retain the input series, completeness status, formula contract, and calculation snapshot hash.
- Existing authoritative utilisation evidence cannot be silently overwritten by workbook approval.

## Acceptance gates

A green CI run is necessary but is **not by itself sufficient** to certify workbook parity. Merge readiness for the original workbook-parity scope requires:

1. One Alembic head and a clean PostgreSQL upgrade on the exact PR head.
2. Exact-numeric and append-only trigger regression tests.
3. All Reliability backend tests.
4. Frontend route, model, lint, production-build, and browser tests.
5. Representative tenant browser UAT across all 16 domains, governed analysis, imports, and reports.
6. Direct audit of all three original workbook files from their actual bytes.
7. Fixture tests comparing source headers, required/hidden sheets, formula behavior, validation lists, and required report outputs against the portal implementation.
8. Resolution of any workbook-specific naming, formula, or layout differences discovered by that direct comparison.
9. A final role/authorization review for create, import, approve, close, mapping, calculation, and report actions.
10. The pull request remains draft until every applicable gate is evidenced on the exact final head.
