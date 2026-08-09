# FAA Reliability Profile

**Official source verified:** 2026-08-07  
**Current FAA source used:** AC 120-17B landing page: https://www.faa.gov/regulations_policies/advisory_circulars/index.cfm/go/document.information/documentid/1035253

## Current source status

FAA currently identifies `AC 120-17B — Reliability Program Methods—Standards for Determining Time Limitations` as active. The AC was originally issued 19 December 2018 and the current FAA publication carries an editorial update dated 09 July 2026.

The AC is advisory guidance. AMO Portal does not treat the AC itself as the binding source of an operator's authority to operate a Reliability Programme or alter maintenance time limitations.

## Mandatory operator-authority gate

`FAA-CFR-OPSPECS-APPLICABILITY` is seeded as:

- mandatory;
- applicable by default;
- `GAP` by default;
- publication blocking;
- operator-current verification required.

Before a report is represented as complete under an FAA profile, the tenant must record the applicable current 14 CFR and OpSpecs/MSpecs/programme authority, including the approved scope and restrictions for maintenance-task or interval adjustments.

## AC 120-17B analytical mapping

The advisory requirements currently mapped into the baseline profile cover the programme elements expected for:

- data collection;
- controlled data quality;
- performance standards/alert levels;
- analysis and recommendation;
- corrective action;
- approval and implementation;
- reporting/display;
- unresolved deficiency/action carry-forward;
- planned/implemented recommendation status;
- effectiveness monitoring;
- programme self-audit and continued adequacy.

Formal report frequency and content remain profile/operator controlled. The software does not infer that every operator has the same FAA programme authority merely because the profile is selected.

## Maintenance-time-limit protection

A formal Reliability AMP recommendation records its technical evidence, review and authority requirement but cannot autonomously change an approved task or interval. Restricted-source tasks and other controlling limitations remain subject to their applicable source and authority controls.

## Profile configuration

- Code: `FAA`
- Baseline version: `2026-08-07.1`
- AC reference: `AC 120-17B`
- Original issue: 2018-12-19
- Current editorial update: 2026-07-09
- Historical windows: 12, 24 and 36 months.
- Binding CFR/OpSpecs applicability is retained separately from AC guidance.
