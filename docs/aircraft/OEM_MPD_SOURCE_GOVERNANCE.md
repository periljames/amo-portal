# OEM Maintenance-Planning Source Governance

## Purpose

This layer establishes the controlled OEM maintenance-planning baseline used by AMO Portal aircraft engineering. It deliberately stops before tenant AMP authoring.

The authority chain is:

```text
OEM controlled publication / MRM / MRB / ALI / CMR / ICA
        ↓
OEM publication revision + active temporary revisions
        ↓
Canonical aircraft content-pack revision
        ↓
Tenant-approved AMP overlay (separate later layer)
        ↓
Aircraft-specific programme and accomplishment baseline
```

An OEM baseline is never edited to represent an operator's AMP. Tenant changes are overlays against an immutable published OEM revision.

## Source-data rule

No proprietary OEM manuals are committed to the source-code repository. The repository contains schemas, import logic, tests and synthetic fixtures only.

Controlled OEM files belong in protected document/object storage. Database records retain their storage locator or controlled URL, SHA-256 identity, revision, effective date, submitter, verifier and audit trail.

A multi-file publication revision such as a Series 400 MPD may register each controlled file as a separate `AircraftContentPackSource` reference while retaining one OEM publication-revision record for the revision baseline. Individual content rows are always tied to an exact source tuple:

```text
source reference + source revision + SHA-256
```

The `provenance_json` must identify the controlled source file or manifest entry when the publication revision consists of multiple files.

## OEM technical-data registry

`AircraftOemPublication` identifies a publication independently from its revisions. Examples include an MPD, MPM/EMP, MRM, AIPC or other ICA publication.

`AircraftOemPublicationRevision` is immutable source identity and follows:

```text
CANDIDATE → VERIFIED → CURRENT → SUPERSEDED
                ↘ REJECTED
CANDIDATE/VERIFIED → WITHDRAWN
```

Only a platform superuser can verify a candidate or promote a verified revision to `CURRENT`. Promotion supersedes the previous current revision rather than overwriting it.

AMO administrators can submit candidate revision metadata and controlled-source references. This enables collaborative technical-data intake without giving a tenant authority to alter the shared global OEM baseline.

## Temporary revisions

Temporary revisions are first-class controlled records. They are not flattened into the base publication revision.

Lifecycle states are:

```text
ACTIVE → INCORPORATED
       → SUPERSEDED
       → REPLACED
       → WITHDRAWN
```

An AMO administrator can submit a temporary revision. A platform superuser verifies it before it may be used as the controlled source of published engineering content.

A replacement temporary revision can identify the TR it replaces. The replaced active TR is retained and marked `REPLACED`.

This is required because OEM temporary revisions can replace previous TRs and can state that their changes are not reflected in the publication appendices. The portal therefore never assumes a base revision and its appendices are internally synchronized when an active TR says otherwise.

## Source baseline statement

Every operational OEM source view must expose a source baseline statement containing at least:

- manufacturer;
- aircraft family and series;
- publication code and title;
- publication kind;
- current verified revision;
- issue/effective date when supplied;
- SHA-256 source or manifest identity;
- active temporary revisions;
- source-file/storage references;
- verification user and timestamp;
- currentness state;
- configured update-watch channels.

The statement is evidence of what the portal used. It is not a claim that the OEM has issued no later material unless the configured source channels have been checked and that fact is recorded.

## Currentness states

The API exposes a deterministic currentness result:

- `NO_CURRENT_REVISION` — no revision has been promoted to current;
- `CURRENT` — a current verified revision exists and no unresolved candidate/TR condition exists;
- `CANDIDATE_REVIEW_REQUIRED` — a later candidate or verified-but-not-promoted revision requires review;
- `TEMPORARY_REVISION_ACTIVE` — one or more verified active TRs form part of the operational source baseline;
- `SOURCE_CHECK_REQUIRED` — source verification is incomplete, for example an active TR is unverified or an enabled watch has never been checked.

## Source-watch abstraction

Publication monitoring is deliberately transport-neutral. Supported channel types are:

- `MANUAL_UPLOAD`
- `OEM_PORTAL`
- `EMAIL_NOTICE`
- `RSS`
- `API`
- `OTHER`

A watch stores the channel reference, last check time, the last observed marker and the check result. It does not scrape protected OEM content. If an OEM later provides a licensed API/feed, that connector can update the same watch/currentness model without changing maintenance-programme logic.

## Canonical MPD requirement model

A canonical task retains both machine-readable scheduling data and the OEM wording needed to explain it.

Core fields include:

- MPD task number;
- ATA chapter;
- programme section;
- task type;
- description;
- machine-readable interval expression;
- original interval text;
- machine-readable effectivity expression;
- original effectivity text;
- source requirement authorities and references;
- task-card and task-card-configuration references;
- AMM/AMTOSS reference;
- zones and panels;
- general preparation/access references;
- skill;
- labour hours and number of persons;
- programme notes;
- packaging metadata;
- exact source page/reference/revision/checksum.

The original text is retained because a normalized expression must never erase controlled source meaning.

## Interval schema

New MPD content uses `MPD_INTERVAL_V1`. Legacy content-pack intervals remain accepted for backwards compatibility.

An interval consists of one or more groups. A group has a phase, a combination mode and controlled limits.

### Phases

- `INTERVAL`
- `THRESHOLD`
- `INITIAL`
- `REPEAT_CUT_IN`
- `REPEAT`
- `LIMIT`

### Combination modes

- `SINGLE`
- `WHICHEVER_FIRST`
- `ALL_DUE`
- `OPPORTUNITY`

### Counter dimensions

- `FH` — aircraft flight hours
- `FC` — aircraft flight cycles
- `EH` — engine hours
- `APUH` — APU hours
- `LANDINGS`
- `DY`
- `MO`
- `YR`
- `STARTS`
- `CUSTOM` — explicitly named non-standard counter, for example unit landings where required by controlled source data

IEEE-754 floating-point input is rejected for controlled intervals. Exact decimal values must use canonical decimal strings.

### Example: whichever occurs first

```json
{
  "schema": "MPD_INTERVAL_V1",
  "groups": [
    {
      "phase": "INTERVAL",
      "mode": "WHICHEVER_FIRST",
      "limits": [
        {"counter": "FC", "value": 25000},
        {"counter": "YR", "value": 12}
      ]
    }
  ]
}
```

### Example: structural threshold / repeat cut-in / repeat

```json
{
  "schema": "MPD_INTERVAL_V1",
  "groups": [
    {"phase": "THRESHOLD", "mode": "SINGLE", "limits": [{"counter": "FC", "value": 40000}]},
    {"phase": "REPEAT_CUT_IN", "mode": "SINGLE", "limits": [{"counter": "FC", "value": 80000}]},
    {"phase": "REPEAT", "mode": "SINGLE", "limits": [{"counter": "FC", "value": 34870}]}
  ]
}
```

### Example: opportunity task

```json
{
  "schema": "MPD_INTERVAL_V1",
  "groups": [
    {
      "phase": "INTERVAL",
      "mode": "OPPORTUNITY",
      "reference": "MRB SYS Note 5"
    }
  ]
}
```

No artificial FH/FC/calendar value is generated for an opportunity requirement.

## Requirement authority and effectivity

The canonical task can carry multiple source requirements. This is required where one MPD task represents more than one source requirement, for example MRB plus CMR.

Source-requirement metadata can retain:

- MRB/MRM/ALI/CMR authority;
- source task number;
- configuration letter;
- MSG-3 FEC path;
- CMR `*` / `**` classification;
- controlling note references;
- model applicability.

Effectivity is stored twice:

1. an explainable machine-readable expression for evaluation; and
2. the exact/raw OEM effectivity text for audit and review.

The expression must be able to represent MSN ranges, pre/post Modsum, pre/post Service Bulletin, options, operating conditions, part numbers and serial-number conditions. A parser must not guess a condition it cannot prove; unresolved text remains a review issue rather than becoming an invented effectivity rule.

## Supporting resources

Not every useful item in an MPD is a maintenance task. `AircraftContentPackResource` stores controlled source-backed supporting data without forcing it into task rows.

Expected resource kinds include:

- access-panel data;
- general references;
- task-card cross references;
- structural component tracking definitions;
- parts/consumables/tools and equipment by task;
- programme notes;
- interval summary/index rows;
- EWIS/zonal packaging relationships;
- recommended parts;
- source tables used for validation or planning.

Every resource has the same exact source tuple and page reference controls as a task.

## Component lineage requirements

The source model is designed for requirements that follow components on and off aircraft. It must support later aircraft-instance tracking for:

- serialized components;
- non-serialized controlled components tracked by a serialized next-higher assembly;
- movement between aircraft;
- calendar ageing while in storage;
- landing-gear top-assembly versus subassembly tracking;
- structural/safe-life component history.

The OEM source pack defines the requirement and eligible component identity. The aircraft-instance ledger implements the operational history; those two concerns are not collapsed into one table.

## Zonal and EWIS packaging

Packaging relationships are advisory planning metadata, not altered task intervals. Where an EWIS requirement should be carried out with a related zonal task on every second/third repeat, the canonical record keeps:

- both independent requirements;
- both independent intervals;
- the packaging relationship/repeat ratio;
- common zone/panel access metadata.

The planning engine can later optimize them into the same event without losing either compliance clock.

## Content-pack publication

A source content-pack revision is created as `DRAFT` and receives a deterministic content hash over sources, tasks, positions, components and supporting resources.

Publication requires:

1. a platform superuser;
2. exact controlled source backing;
3. the expected content hash from review;
4. at least one controlled engineering item;
5. source registry verification for registry-linked sources.

Publishing supersedes the previous published revision. It never updates that revision in place.

## Revision comparison

The API can compare two revisions of the same content pack and returns:

- added tasks;
- removed tasks;
- changed tasks;
- unchanged task count;
- added resources;
- removed resources;
- changed resources.

This is the base mechanism for the later impact workflow:

```text
new OEM revision / TR
      ↓
old canonical baseline ↔ proposed new baseline
      ↓
changed requirements/effectivity/resources
      ↓
identify affected tenant AMPs
      ↓
controlled AMP revision proposal
```

The AMP-impact portion is intentionally deferred to the tenant-programme layer.

## Dash 8 family source packs

Bootstrap creates separate source-intake packs for Series 100, 200, 300 and 400 in addition to the family scaffold. This prevents Series 400 constructs from being silently copied into a Series 100/200/300 programme and allows common family content to be introduced deliberately where supported by source evidence.

## Series 400 constructs used to validate the model

The Series 400 MPD supplied for development exposed the following requirements that shaped the schema:

- Systems & Powerplant, Structures and Zonal programmes are distinct sections;
- MRB, CMR and ALI source authorities can coexist;
- the more restrictive MRB/CMR interval may control an MPD task;
- task applicability can depend on MSN, Modsum, SB, option and part/SN condition;
- intervals include FH, FC, engine hours, APU hours, calendar units, threshold, initial interval, repeat cut-in and repeat;
- structural tasks may provide alternative DET/SDI methods subject to approved programme control;
- opportunity tasks exist and cannot be represented by a fabricated numeric interval;
- component history must remain traceable on/off aircraft and through storage;
- access-panel, task-card, AMM, labour and resource data are operationally useful supporting content;
- EWIS/zonal packaging can be based on shared access and repeat multiples;
- Temporary Revisions can replace earlier TRs and may explicitly state that appendices have not yet been updated.

These are treated as aircraft-engineering domain rules, not Q400-specific UI hacks.

## Deliberately deferred

Tenant AMP configuration is not part of this layer. The next layer will inherit a selected published OEM baseline and record tenant-approved `SAME`, `MODIFY`, `ADD` or controlled exclusion/deviation decisions without changing the OEM record.

Aircraft-status workbook migration is also downstream. Existing aircraft Excel values will be reconciled against the canonical OEM/AMP requirement identities rather than being copied blindly into the source library.
