# Reliability Regulatory Requirements Matrix

**Access/verification date:** 2026-08-07  
**Authoritative implementation:** versioned records in `reliability_regulatory_profiles` and `reliability_regulatory_requirements`.

This document is an explanatory index. It does not establish legal compliance and it does not replace the machine-readable requirement/version records retained by AMO Portal.

## Source precedence

1. Applicable binding regulation, authority approval/condition and OpSpecs/MSpecs.
2. The operator's accepted/approved Reliability Programme and maintenance programme.
3. Applicable authority AMC/GM/AC/advisory material.
4. Approved OEM/MRB/MSG-3 material within its effectivity and restrictions.
5. Operator/OEM benchmark material used only for analytical and usability benchmarking.

## Baseline matrix

| Requirement key | Authority | Source / current verification basis | Obligation in baseline | Default report status | Publication effect | Portal implementation |
| --- | --- | --- | --- | --- | --- | --- |
| `KCAA-CURRENT-REGULATORY-MAPPING` | KCAA | Kenya Civil Aviation Regulations 2025 + tenant accepted/approved programme; KCAA 2025 publication/transition page | Mandatory | `GAP` | Blocks | Exact current paragraph/programme basis must be recorded before KCAA-profile publication can be represented as complete. |
| `KCAA-AWS010D-PERIODIC-REPORT-CONTENT` | KCAA | `CAA-AC-AWS010D Reliability Programme`, Rev D/effective 2018-07-01 | Advisory/legacy | `WITHHELD` | Profile controlled | Maps periodic fleet/utilisation, operational-interruption, trend and corrective-action guidance to formal chapters. |
| `KCAA-AWS010D-LONG-TERM-TREND` | KCAA | `CAA-AC-AWS010D` long-term trend guidance | Advisory/legacy | `WITHHELD` | Profile controlled | Historical windows are configured separately from the interactive current-period dashboard. |
| `EASA-MA302-APPLICABILITY-AND-AMP-CONTROL` | EASA | Regulation (EU) No 1321/2014, M.A.302 and current continuing-airworthiness rules | Mandatory | `GAP` | Blocks | Requires applicability/AMP-control evidence. A Reliability recommendation never mutates the approved AMP directly. |
| `EASA-AMC-MA302-DATA-ANALYSIS-CORRECTIVE-ACTION` | EASA | Appendix I to AMC M.A.302, current Easy Access Rules | Advisory | `WITHHELD` | Profile controlled | Maps controlled data, trend/repetitive-defect analysis, corrective action and effectiveness evidence. |
| `EASA-AMC-MA302-REPORTING-EFFECTIVENESS` | EASA | Appendix I to AMC M.A.302 | Advisory | `WITHHELD` | Profile controlled | Maps responsibility, reporting/distribution, effectiveness review and controlled programme amendment. |
| `FAA-CFR-OPSPECS-APPLICABILITY` | FAA | Applicable 14 CFR + tenant current OpSpecs/MSpecs authority | Mandatory | `GAP` | Blocks | Operator-specific authority/scope must be recorded rather than inferred from AC 120-17B. |
| `FAA-AC12017B-PROGRAMME-ELEMENTS` | FAA | AC 120-17B, original 2018-12-19; editorial update 2026-07-09 | Advisory | `WITHHELD` | Profile controlled | Maps data collection, standards, analysis/recommendation, approval/implementation and reporting/display. |
| `FAA-AC12017B-REPORTING-DISPLAY` | FAA | AC 120-17B Chapter 7 | Advisory | `WITHHELD` | Profile controlled | Maps trends, unresolved deficiencies/actions, recommendations and effectiveness monitoring. |
| `OPERATOR-PROGRAMME-MAPPING` | Operator | Tenant accepted/approved Reliability Programme | Mandatory | `GAP` | Blocks | Operator report cycle, methods, approval chain, authority conditions and required sections must be configured. |

## Current official sources

### KCAA

- Regulations 2025: https://www.kcaa.or.ke/legislation-publications/regulations-2025
- Airworthiness Advisory Circulars: https://www.kcaa.or.ke/legislation-publications/advisory-circulars
- `CAA-AC-AWS010D — Reliability Programme` is still published by KCAA but was issued against the 2018 framework. It is retained as legacy/advisory guidance and is **not** used as conclusive evidence that KCARs 2025 requirements are satisfied.

### EASA

- Easy Access Rules for Continuing Airworthiness, September 2025 revision: https://www.easa.europa.eu/en/document-library/easy-access-rules/easy-access-rules-continuing-airworthiness
- Implementation focuses on M.A.302 and Appendix I to AMC M.A.302 where applicable, including programme applicability, data/analysis, corrective action, effectiveness, reporting and maintenance-programme amendment control.

### FAA

- AC 120-17B landing page: https://www.faa.gov/regulations_policies/advisory_circulars/index.cfm/go/document.information/documentid/1035253
- FAA identifies AC 120-17B as active and currently shows an editorial update dated 2026-07-09. The AC remains guidance; applicable CFR and operator OpSpecs/MSpecs are separately controlled.

## Evidence-state rules

Per-report requirement assessments use only:

- `SATISFIED`
- `NOT_APPLICABLE`
- `WITHHELD`
- `GAP`
- `SUPERSEDED`

`SATISFIED` requires a reviewer note plus a retained source/calculation/evidence reference. `NOT_APPLICABLE` requires a recorded applicability rationale. Mandatory applicable `GAP` items block controlled advancement/publication unless an explicitly authorised and audited exceptional override is created.

## Versioning rule

A regulatory change creates a new requirement/profile version. Historical reports retain the exact prior requirement snapshot and source manifest. Regulatory evidence is never rewritten destructively to make an older report appear to have been assessed against a later rule.
