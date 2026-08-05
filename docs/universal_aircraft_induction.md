# Universal Aircraft Type Library and Induction

## Purpose

The portal builds an aircraft type once, applies an approved tenant programme overlay once per operator, and inducts every tail from its actual configuration, counters, status, and records.

This architecture replaces the former aircraft/component importer and the Phase 4 migration-batch workflow. There is one onboarding API, one cockpit, one reconciliation lifecycle, and one activation manifest.

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

## Global reusable content

A published type-template revision is immutable and can include:

- family, type, variant, and type-certificate identity;
- MPD, MRB, CMR, ALI, ICA, AD, SB, STC, and authority references;
- configuration hierarchy and positions;
- allowable part numbers and quantities;
- counter rules;
- maintenance requirements, thresholds, intervals, and governing logic;
- structured effectivity.

A new revision supersedes the previous published revision. Existing aircraft remain bound to their approved revision until a controlled re-baseline is performed.

## Tenant programme overlay

A tenant programme revision references the current published aircraft-type revision and stores only operator differences:

- `ADD`: operator or authority requirement;
- `MODIFY`: approved change to inherited content;
- `EXCLUDE`: approved exclusion with justification;
- overlay effectivity;
- authority approval reference and date.

Approved tenant revisions are immutable.

## Explainable effectivity

Effectivity is structured JSON rather than executable formulas.

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

Results include human-readable explanations of every matched and unmatched criterion.

Logical operators: `all`, `any`, `not`.

Comparisons: `eq`, `neq`, `in`, `not_in`, `between`, `exists`, `contains`, `contains_any`, `contains_all`, `prefix`, `gt`, `gte`, `lt`, `lte`.

## Source mappings are separate

`ImportMappingProfile` answers: **How is this source layout interpreted?**

`AircraftTypeTemplateRevision` answers: **What engineering structure and requirements apply?**

The same WinAir, AMOS, TRAX, Ramco, CSV, or workbook mapping can therefore be reused across tenants and aircraft types without duplicating engineering content.

## Supported induction datasets

One induction may contain multiple files and sheets with different schemas:

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

CSV, XLSX, XLSM, and XLSB are parsed read-only. XLSB support is provided through the dedicated binary-workbook adapter so current DHC8 source workbooks can be staged without conversion.

## Lifecycle

```text
DRAFT -> STAGED -> VALIDATED -> EFFECTIVITY_RESOLVED -> APPROVED -> ACTIVE
```

Activation creates:

- aircraft master;
- actual installed configuration;
- opening canonical FH/FC ledger entry;
- persisted counter baselines;
- revision-specific AMP task materialisation;
- active AMP aircraft baseline;
- applicability snapshot and hash;
- active aircraft template binding;
- activation manifest and audit event.

Existing aircraft cannot be silently re-inducted.

## Removed architecture

The registered application no longer exposes:

- `/aircraft/import/*`;
- component-specific import APIs;
- OCR importer APIs;
- importer preview/session/snapshot APIs;
- `/integrations/migration/*` APIs;
- migration-batch rollout linkage.

The migrations convert reusable old mappings to `ImportMappingProfile`, drop retired importer tables, rename rollout lineage to `induction_id`, and remove migration-batch tables.

## Rollout gate

Dual run requires:

- active universal induction;
- active aircraft type/programme/applicability binding;
- canonical utilization ledger;
- active approved AMP baseline;
- no open Technical Records exceptions.

## Initial content packs

Build and validate:

1. Cessna 208 / 208B / 208B EX;
2. DHC8-100 / 200 / 300.

Existing workbooks remain source and validation evidence, not permanent template structures.

## Verification before merge

1. Upgrade Alembic through `j0k1l2m3n4o5` on disposable PostgreSQL.
2. Initialize all SQLAlchemy mappers and inspect metadata.
3. Run backend unit and API integration tests.
4. Run TypeScript typecheck and Vite production build.
5. Author C208 and DHC8 type revisions.
6. Run a multi-file 5Y-SLS and 5Y-SLK induction rehearsal.
7. Test global versus tenant-private visibility.
8. Test rollout transitions using `induction_id`.
