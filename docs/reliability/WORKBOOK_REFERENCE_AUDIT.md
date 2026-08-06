# Reliability Workbook Reference Audit

Date: 2026-08-06

This audit records the structural and analytical baseline recovered from the three supplied operator workbooks. The workbooks are reference evidence only. The portal database, controlled source registers, approved calculation snapshots and retained reports are authoritative.

## Source fingerprints

| Reference | SHA-256 | Size | Sheets | Hidden | Formulas | Cached formula errors | Charts | External links | VBA |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| C208B Reliability Programme | `693bf6ec4cec3fbb062a9fcd35760f750f1813dae7009001ebb3c2a6d34741fc` | 4,740,592 bytes | 12 | 1 | 2,990 | 66 `#DIV/0!` | 1 | 1 | Present, unsigned |
| Historical Analysis Template | `aa48fa30c9eec96c3b97e684e50a8acbee948e20bd30addcd9eb60d8dd6b3c6c` | 4,743,367 bytes | 75 | 58 | 42,777 | 1,640 `#DIV/0!`, 833 `#REF!`, 12 `#N/A`, 2 `#VALUE!` | 451 | 1 | None |
| DHC8 Reliability Programme | `259acbac9752dd6f6fdd9c222d9da92b6e10e48bacbd8544683bd8bbb3f15000` | 4,465,878 bytes | 18 | 2 | 23,888 | 10,787 `#DIV/0!`, 24 `#NUM!` | 4 | 0 | Present, unsigned |

The workbooks are not accepted as tamper-resistant operational stores because they include unsigned VBA, external links, hidden formula/report areas, broken defined names, mutable thresholds and formula-error propagation. The portal never executes VBA, never follows external links and never accepts formula results as controlled source values.

## Controlled source domains

The portal catalogue covers all operational workbook source domains and the additional governed portal domains:

`AU`, `AI`, `FI`, `PM`, `OOS`, `RM`, `SM`, `SR`, `SB`, `CS`, `AS`, `UR`, `STRUCTURES`, `RECURRING`, `ECTM`, and `ADD`.

The DHC8-specific `SB`, `CS`, `AS`, and component `UR`/`MTBUR` analysis contracts are explicitly represented. Aircraft registration and manufacturer serial number remain distinct identities and are resolved against the tenant fleet before an import row can be queued.

## Analytical methods

### Exact sample-sigma method

The portal uses fixed-point `Decimal` arithmetic:

- Mean: `Σx / n`
- Sample standard deviation: `sqrt(Σ(x - mean)^2 / (n - 1))`
- Warning: `mean + warning_multiplier × sample_standard_deviation`
- Alert: `mean + alert_multiplier × sample_standard_deviation`

At least three valid periods are required. Missing periods are not silently replaced with zero.

### Workbook-reference method

For continuity with the supplied programme workbooks, the portal retains a separately labelled 12-period reference method:

- Population sigma over the latest 12 consecutive periods.
- Population sigma of the 11 adjacent two-period means.
- Warning: `mean + moving_mean_sigma + 2 × population_sigma`.
- Alert: `mean + moving_mean_sigma + 3 × population_sigma`.

This method is never presented as the statistically preferred method. It is withheld when any baseline exposure is missing.

### Variable-exposure event rates

For rates based on flight hours or flight cycles, the portal supports a Poisson u-chart:

- Centre: `Σevents / Σexposure × scale`.
- Period sigma: `sqrt(centre × scale / period_exposure)`.
- Each period retains its own warning and alert limits.
- The default scale is 1,000, matching the C208B and DHC8 programmes.
- A legacy per-100-flight-hour route remains available only for compatibility.

### Component removal analysis

The DHC8 component analysis is represented with exact calculations:

- Exposure unit-hours: `quantity_per_aircraft × fleet_unit_hours`.
- URR per 1,000 unit-hours: `unscheduled_removals / exposure × 1,000`.
- MTBUR: `exposure / unscheduled_removals`.
- Total removal rate per 1,000 unit-hours: `total_removals / exposure × 1,000`.
- MTBR: `exposure / total_removals`.

Zero-removal periods produce an explicit no-event status and a withheld MTBUR/MTBR value instead of `#DIV/0!`.

## Tamper-resistance controls

- Exact fixed-point database storage for legacy Reliability trends and KPIs.
- Source workbook SHA-256, structural fingerprint, selected-sheet state, header row and row SHA-256 evidence.
- Profile-specific required-sheet matching for the C208B and DHC8 references.
- Hidden sheets are not importable.
- Formula and formula-error cells are rejected when mapped to controlled fields.
- The historical analysis template is audit-only and cannot be committed as operational source evidence.
- Imported evidence is created only as `DRAFT` and requires a separate approval action.
- Approved and closed workbook records are database-immutable; corrections require a superseding revision.
- Statistical results and retained report snapshots are append-only at database level.
- Completed import batches and their row evidence are immutable at database level.
- Every governed statistical result includes the exact input series, exact values, completeness status, formula text and SHA-256 calculation snapshot.
- A pre-existing authoritative utilisation row cannot be silently overwritten by workbook approval.

## Acceptance gates

The branch is not ready merely because workbook outputs look similar. Merge readiness requires:

1. One Alembic head and a clean PostgreSQL upgrade.
2. Exact-numeric and append-only trigger regression tests.
3. All Reliability backend tests.
4. Frontend route, model, lint and production-build tests.
5. Representative tenant browser UAT across all 16 domains, governed analysis, imports and reports.
6. The pull request must remain draft until the exact head records green results for every gate.
