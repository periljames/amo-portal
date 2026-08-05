# Universal Aircraft Type Library and Induction

## Purpose

The portal builds an aircraft type once, applies an approved tenant programme overlay once per operator, and then inducts each tail from its actual configuration, counters, status, and records.

The architecture replaces the former aircraft/component importer and the Phase 4 migration-batch workflow. There is one onboarding API, one cockpit, one reconciliation lifecycle, and one activation manifest.

## Canonical model

```text
Aircraft Family
  -> Certified Type
    -> Variant
      -> Type Template
        -> Immutable Type Template Revision
          -> Source Documents
          -> Allowable Configuration
          -> Maintenance Requirements and Effectivity

Tenant Maintenance Programme
  -> Approved Tenant Programme Revision
    -> References one published Type Template Revision
    -> Stores only controlled ADD / MODIFY / EXCLUDE overlays

Aircraft Induction
  -> Variant + Type Revision + Tenant Programme Revision
  -> Multiple classified source datasets
  -> Versioned source mapping profiles
  -> Row validation and decisions
  -> Actual-configuration conformity
  -> Explainable applicability snapshot
  -> Quality approval
  -> Aircraft activation and immutable baseline binding
```

## What is global and reusable

The type library can contain global or tenant-private templates. A published revision is immutable and includes:

- aircraft family, type, variant, and type-certificate identity;
- source MPD, MRB, CMR, ALI, ICA, AD, SB, STC, and authority references;
- configuration hierarchy and positions;
- allowable part numbers and quantities;
- counter rules;
- maintenance requirements, thresholds, intervals, and governing logic;
- structured effectivity.

A new revision supersedes the previous published revision. Existing aircraft remain bound to the revision that was approved for them until a controlled re-baseline is performed.

## Tenant programme overlay

A tenant programme revision must reference the current published aircraft-type revision. It stores only operator differences:

- ADD: approved operator or authority requirement;
- MODIFY: approved change to an inherited requirement;
- EXCLUDE: approved exclusion with justification;
- optional overlay effectivity;
- authority approval reference and approval date.

Approved tenant revisions are immutable. A new approval supersedes the prior revision.

## Explainable effectivity

Effectivity is represented as structured JSON, not executable formulas or arbitrary code.

```json
{
  "all": [
    {"field": "aircraft.variant_code", "operator": "eq", "value": "DHC8-315"},
    {"field": "aircraft.msn", "operator": "between", "value": [300, 620]},
    {"field": "configuration.part_numbers", "operator": "contains", "value": "PW123-ABC"},
    {"not": {"field": "modifications", "operator": "contains", "value": "MOD-8-3021"}}
  ]
}
```

Every result includes explanations such as:

```text
aircraft.variant_code matched: actual='DHC8-315', operator=eq, expected='DHC8-315'
aircraft.msn matched: actual=487, operator=between, expected=[300, 620]
NOT: modifications did not match: actual=['MOD-8-1001'], operator=contains, expected='MOD-8-3021'
```

Supported logical operators: `all`, `any`, `not`.

Supported comparisons: `eq`, `neq`, `in`, `not_in`, `between`, `exists`, `contains`, `contains_any`, `contains_all`, `prefix`, `gt`, `gte`, `lt`, `lte`.

## Source mappings are not aircraft templates

`ImportMappingProfile` answers: **How is this source layout interpreted?**

`AircraftTypeTemplateRevision` answers: **What engineering content and configuration apply to the aircraft type?**

They are separate domains.

Mapping profiles are versioned and identified by:

- source system and version;
- canonical dataset;
- deterministic schema fingerprint;
- normalized header signature;
- source-to-canonical mapping;
- transformations, defaults, and validation.

The same WinAir, AMOS, TRAX, Ramco, or spreadsheet export mapping can be reused across tenants and aircraft types without duplicating engineering templates.

## Supported induction datasets

One job may contain multiple files and sheets with different schemas:

- `AIRCRAFT_MASTER`
- `CONFIGURATION`
- `COMPONENTS`
- `LLP_STATUS`
- `UTILISATION`
- `AMP_STATUS`
- `AD_STATUS`
- `SB_STATUS`
- `MODIFICATIONS`
- `REPAIRS`
- `DEFERRALS`
- `MAINTENANCE_HISTORY`
- `DOCUMENT_INDEX`

CSV, XLSX, and XLSM are parsed directly. XLSB must be exported to XLSX or handled by a source-system adapter because safe binary-workbook parsing is not part of the web application runtime.

## Induction lifecycle

```text
DRAFT
  -> STAGED
  -> VALIDATED
  -> EFFECTIVITY_RESOLVED
  -> APPROVED
  -> ACTIVE
```

Activation creates or binds:

- aircraft master;
- actual installed configuration;
- opening canonical FH/FC ledger entry;
- persisted counter baselines;
- revision-specific AMP task materialisation;
- active AMP aircraft baseline;
- applicability snapshot and hash;
- active aircraft template binding;
- activation manifest and audit event.

Existing aircraft cannot be silently re-inducted. A separate controlled re-baseline workflow must be used.

## Removed architecture

The registered application no longer exposes:

- `/aircraft/import/*`
- component-specific import APIs;
- OCR importer APIs;
- importer preview/session/snapshot APIs;
- Phase 4 `/integrations/migration/*` APIs;
- migration-batch rollout linkage.

The database migration converts reusable old column mappings to `ImportMappingProfile`, drops retired importer tables, renames rollout lineage to `induction_id`, and drops migration-batch tables.

## Rollout gate

An aircraft cannot enter dual run unless it has:

- an active universal induction;
- an active aircraft template binding;
- a canonical utilization ledger;
- an active approved AMP baseline;
- no open Technical Records exceptions.

## Initial content packs

The first controlled type-library content should be built for:

1. Cessna 208 / 208B / 208B EX family;
2. DHC8-100 / 200 / 300 family.

Existing aircraft workbooks are source and validation evidence. They are not the permanent template structure.

## Verification before merge

Run:

1. Alembic upgrade through `j0k1l2m3n4o5` on a disposable PostgreSQL copy.
2. SQLAlchemy mapper initialization and metadata inspection.
3. Backend unit and API integration tests.
4. TypeScript typecheck and Vite production build.
5. C208 and DHC8 type-revision authoring tests.
6. Multi-file 5Y-SLS induction dry run and rollback rehearsal.
7. Cross-tenant visibility tests for global versus tenant-private templates and mappings.
8. Rollout transition tests using `induction_id`.
