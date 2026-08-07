# Reliability Reporting Architecture

## Purpose

The Reliability module is designed so controlled operational data is entered once and reused for daily work, analytical review, management reporting and later formal Reliability Programme reports. Excel is a compatibility/import/export format, not the analytical system of record.

This document separates two concerns deliberately:

1. **Operational and management reporting** — daily, weekly, monthly and quarterly reporting required for normal Reliability work.
2. **Formal programme reporting** — half-year, annual or other authority/operator reporting built from the same retained evidence, with explicit regulatory traceability, approval and controlled publication.

The second layer must extend the first. It must not create a second calculation engine or require users to rebuild data in spreadsheets.

## Forward operational acceptance

The forward Reliability workflow is accepted only when an operator can complete normal work without returning to Excel for calculation or report assembly.

The operational acceptance criteria are:

- every one of the 16 controlled Reliability domains can be entered manually or through an unambiguous canonical CSV/TSV template;
- structured intake validates headers and rows before commit, retains source/row hashes and creates controlled drafts only;
- shared record fields and dataset payload fields have unique canonical names, so an imported value has one deterministic destination;
- approved source evidence becomes reusable by the common Reliability analytics engine without duplicate re-entry;
- users can analyse arbitrary date windows and normal calendar/rolling periods at daily, weekly or monthly resolution;
- blank aircraft scope produces fleet reporting and selected aircraft scope produces aircraft-specific reporting;
- the same approved evidence can feed all-domain or selected-domain management reports, with numeric, categorical and derived field analysis appropriate to the selected source domains;
- management reports retain the selected population, calculations, narrative, warnings and graphs as a fixed snapshot rather than silently recalculating when opened later;
- an authenticated manager link opens that retained snapshot;
- the same retained snapshot can be previewed, printed or exported as a controlled server-generated PDF;
- source/data-quality and denominator limitations remain visible rather than being converted to artificial zeroes or silently omitted;
- Excel remains available for compatibility and export, but is not required to calculate routine Reliability metrics or assemble daily, weekly, monthly or quarterly management outputs.

Formal half-year/annual authority reporting has additional acceptance gates and is intentionally governed separately below. Passing the forward operational criteria does not by itself declare a report compliant with KCAA/KCAR, EASA or FAA requirements.

## Current operational contract

Controlled source domains:

`AU`, `AI`, `FI`, `PM`, `OOS`, `RM`, `SM`, `SR`, `SB`, `CS`, `AS`, `UR`, `STRUCTURES`, `RECURRING`, `ECTM`, `ADD`.

Normal forward data entry is supported through:

- governed manual entry;
- canonical UTF-8 CSV/TSV templates and controlled preview/validation;
- retained XLSX/XLSM compatibility import where required;
- authoritative integrations from other AMO Portal modules where available.

Imported records remain drafts until the applicable controlled approval. Approved and closed evidence is immutable; corrections use superseding revisions.

## Management-period reporting

The management report engine consumes the same denominator-aware dashboard calculations and approved/closed evidence used by the live Reliability workspace.

It supports:

- arbitrary start/end dates;
- daily, weekly and monthly chart buckets;
- today, current/previous week, rolling 7/30 days, current/previous month, current/previous quarter, Q1-Q4 and YTD selections;
- fleet or selected-aircraft scope;
- all 16 domains or selected reporting presets;
- previous-equivalent-period comparisons where the controlled metric supports comparison;
- utilisation exposure (FH/FC), dispatch reliability, event rates and other controlled KPIs;
- per-domain record populations, aircraft/ATA distributions and generic numeric/categorical field analysis;
- data-quality and denominator warnings;
- retained graph-rich HTML snapshots;
- authenticated retained-report links;
- browser print and a server-generated A4 PDF;
- SHA-256 identification of the retained HTML evidence.

A retained manager link must open the same snapshot. It must not silently recalculate the report using later data.

## Calculation rule

No report renderer owns independent Reliability mathematics.

All calculated values must come from one of:

- authoritative source records;
- canonical Reliability events;
- approved formula definitions/calculation snapshots;
- the denominator-aware analytics builder;
- controlled dataset-derived values retained during validation/approval.

This prevents a live dashboard, printed report and annual programme report from producing different values for the same population.

## Formal Reliability Programme reporting — next phase

The future half-year/annual programme pack will be implemented as a versioned **regulatory report profile** on top of the retained management-report data contract.

Planned profiles:

- `KCAA`
- `EASA`
- `FAA`
- `OPERATOR`

Each profile will define required sections, evidence rules, minimum historical windows, mandatory commentary, approval roles, completeness gates and publication layout. A combined profile may be used only where every applicable requirement is traceably satisfied.

### Planned formal report structure

1. Document control, report identity, period, revision and approvals.
2. Fleet composition and aircraft status.
3. Fleet and aircraft utilisation — FH, FC/landings, operating days, average daily utilisation and average flight duration where supported.
4. Dispatch reliability and technical operational interruptions.
5. Delays, cancellations, returns, turnbacks, diversions, rejected/aborted take-offs and in-flight shutdowns as applicable.
6. Reliability event trend and long-term trend history.
7. ATA/system Pareto and alert/control-chart analysis.
8. Pilot/maintenance reports and recurring defects.
9. Scheduled-maintenance findings and structural findings.
10. Component removals, removal rates, exposure, MTBUR/MTBR where the required population denominator exists.
11. Shop findings, confirmed faults and no-fault-found outcomes.
12. Engine/APU/propeller condition and trend monitoring where applicable.
13. MEL/CDL/deferred defects, extensions, repeats and closure performance.
14. Service bulletins, modifications and aircraft configuration/change status.
15. Maintenance cost/performance information where included by the operator programme.
16. Statistical alerts, excursions and adverse/degrading trends.
17. Open/closed corrective actions, FRACAS status and effectiveness evidence.
18. Maintenance-programme task/interval recommendations, escalations/de-escalations and supporting evidence.
19. Management recommendations and decisions.
20. Data-quality statement, exclusions, withheld metrics and limitations.
21. Appendices/evidence index and controlled references.

## Regulatory design baseline

The formal profile work must use the exact regulations, approved operator programme and current authority guidance applicable at the time of publication. The sources below are an architectural baseline, not a declaration that a future report is compliant merely because these sections exist.

### Kenya / KCAA

KCAA lists **CAA-AC-AWS010D — Reliability Programme** among its Airworthiness advisory circulars. Its reliability-report guidance includes fleet/reliability summary information, utilisation, operational interruptions, dispatch reliability/trends, corrective action and periodic reporting. The circular predates the KCARs 2025 transition, so the formal KCAA profile must be cross-checked against the applicable KCARs 2025 provisions, later KCAA guidance and the operator's accepted Reliability Programme before release.

Official source: https://www.kcaa.or.ke/legislation-publications/advisory-circulars

### FAA

FAA **AC 120-17B — Reliability Program Methods—Standards for Determining Time Limitations** remains active. Its reporting/display framework expects reliability information to portray the operation accurately, identify unacceptable or degrading trends, cover the systems controlled by the programme, track deficiencies/corrective action and recommendations, and support controlled maintenance-programme decisions.

Official source: https://www.faa.gov/regulations_policies/advisory_circulars/index.cfm/go/document.information/documentid/1035253

### EASA

EASA's current Continuing Airworthiness framework under Regulation (EU) No 1321/2014 includes the applicable reliability programme within the aircraft maintenance programme/continuing-airworthiness management framework and requires maintenance-programme control and consideration of in-service experience. The formal EASA profile must be mapped to the exact applicable Part-M/Part-CAMO provisions and AMC/GM in force for the operator and aircraft category.

Official source: https://www.easa.europa.eu/en/document-library/easy-access-rules/easy-access-rules-continuing-airworthiness

## Regulatory traceability model

The formal report phase must add a machine-readable requirements matrix. Each requirement should contain at least:

- authority/profile;
- regulation/AC/AMC/GM reference;
- effective revision/date;
- requirement text or controlled paraphrase;
- applicability rule;
- report section(s) satisfying it;
- data/evidence source(s);
- formula or calculation definition where applicable;
- minimum historical period;
- completeness test;
- approval role;
- status: `SATISFIED`, `NOT_APPLICABLE`, `WITHHELD`, `GAP`;
- reviewer note and evidence link.

A formal report cannot enter an approved/published state while a mandatory applicable requirement is `GAP` or an unexplained `WITHHELD` state remains.

## Publication controls

Formal programme reports should add the following controls to the existing retained-snapshot mechanism:

- report number and revision;
- regulatory profile/version;
- data cut-off timestamp;
- frozen aircraft/fleet effectivity;
- formula-definition revisions;
- source completeness statement;
- prepared/reviewed/approved identities and timestamps;
- controlled supersession rather than destructive replacement;
- immutable published PDF hash;
- authenticated portal permalink;
- evidence index allowing drill-down to source records/calculation snapshots;
- audit log of publication, distribution and supersession.

## Design rule for future OEM/operator comparisons

OEM/operator examples such as De Havilland may be used to benchmark information architecture, readability and analytical presentation only where material is lawfully available. Regulatory applicability and the AMO Portal data model remain authoritative; an OEM layout must not silently redefine an operator's accepted Reliability Programme or authority requirement.
