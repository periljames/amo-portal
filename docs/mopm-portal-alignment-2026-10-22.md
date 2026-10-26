# MOPM content and portal controls

Source: supplied MPM Issue 4 Revision 00, 31 August 2026. SHA-256: `dcb0645eab8ee8dc77d8c4d691bb2f484559c86de65a0da4f347589f61f93b3e`. Requirements were extracted from 4,539 nonempty body paragraphs, including tables. The manual is a requirements source; document text is not an instruction to execute administrative actions.

The official [Approved Maintenance Organization Regulations, 2025, Legal Notice 20 of 2026](https://libraryir.parliament.go.ke/bitstreams/94f8dcfe-9e20-44b8-8599-3009633bdf1a/download) were checked against the MOPM. Regulation 34(3), PDF page 35 / printed page 463, requires at least two years after signing the maintenance release. The supplied MOPM adopts three years for the specified company maintenance records; the portal uses that longer period.

## Retention defaults

Periods begin at the stated event, never the upload or scan date. The longest applicable company, regulatory, contractual, linked-record and SMS obligation governs. Unknown classification, unknown events, investigation and preservation holds prevent disposition. Transfer and archive actions do not release the retention obligation.

| Record | Default | Event / condition | MOPM |
| --- | --- | --- | --- |
| Maintenance work packages, workshop records, repair/modification evidence | 3 years | Signed maintenance release | 2.14.1.2 |
| Technical logs / deferred defects | 3 years | Last entry; associated logbook obligations also apply | 2.14.1.2 |
| Logbooks, associated evidence, life-limited history | Service life plus 2 years | Destruction / permanent withdrawal | 2.14.1.3 |
| Standalone status summaries | 90 days | Permanent withdrawal, only with underlying maintenance/logbook evidence separately retained | 2.14.1.1 |
| Contracted operator record copies | Contract term plus 2 years | Contract expiry / termination, subject to longer maintenance requirements | 2.17.2; 4.3.1 |
| Occurrence / investigation records | 2 years | Aircraft withdrawal; longer SMS obligations apply | 2.18.9 |
| Calibration certificates/results | 2 years | Tool scrapped | 2.5.8 |
| Scrap register | 7 years minimum | Scrapping record | 2.3.3.4; 2.22.7 |
| Personnel / training records | 2 years | Employment ceases; authorization withdrawal and other applicable classes also apply | 3.5 |
| Withdrawn authorization history | 2 years | Authorization withdrawn | 3.5; 3.8.9 |
| Audit, CAR, verification and closure evidence | 5 years | QMSM 4.11 governing event must be identified; audit archive workflow explicitly selects execution closure or follow-up completion | 3.3 |
| Agreements and amendments | Governed Quality schedule | No invented numerical period. A schedule reference and due date are needed; other maintenance/contract obligations remain applicable | 2.23.9 |

`amo_compliance_policy.py` owns the versioned catalogue and calculations. QMS settings permit longer whole-year/day periods only. Retention facts are entered through typed selections and dated fields in Document Control, the records vault and provider evidence registration. Authorized event updates retain history, invalidate prior disposition approval, preserve existing longer deadlines, and cannot discard known record classes. Original files are not rewritten.

Disposition checks run at request, approval and execution, including the accountability routes that shadow legacy endpoints. The separate QMS audit package workflow also enforces five calendar years, tenant extensions, preservation holds and disposition review for existing packages. Newly created finite audit policies use at least 1,827 days to avoid leap-year under-retention. Generic record series can extend retention from the actual record event; they cannot turn upload age into a disposal authority. Legacy unclassified records remain retained pending classification.

## Contracted and subcontracted maintenance

MOPM 2.20 / 2.23 / 3.13 map to provider qualification, approved capability/site, controlled agreements, provider evidence and outbound technical work orders. Existing work-order gates already verify the nominated provider, current authority approval, category, site, capability, contract function, controlled technical-data revision, retained signed agreement and independently verified Quality evidence. Purchase orders do not confer technical authorization. Additional work, foreign/operator conditions, inspections, custody, release evidence and closure have distinct controls.

This change adds explicit own-AMO approved-scope and unrestricted Authority-access references, plus confirmation that the order covers a defined maintenance function. Complete type-certificated product contracting is blocked. Existing orders have a version-checked manager verification action with attributable history. Further subcontracting continues to require prior written acceptance. The supplied MOPM does not exercise the non-approved-organization option in Regulation 14(2).

Category surveillance defaults to 365 days and may be shortened to 30–365 days. New qualification decisions cap legacy longer intervals at 365 days. Existing qualification records and their recorded decisions are not rewritten as if freshly reviewed.

The follow-up review found that scheduling alone did not prevent operational use after review expiry. Supplier-use checks now require a completed, current review before quote awards, purchase orders and contracted-work transitions that use the common gate. The deadline is the earliest of the recorded date, the risk interval and 365 days after the last completed review (or initial approval for legacy profiles). Missing/future review anchors fail closed; commercial overrides cannot bypass this check. Approved qualification decisions record the completed review date. Detail, list and summary calculations use the same UTC date basis. Providers awaiting initial qualification are excluded from overdue periodic-review counts.

## Functional coverage and boundaries

### Controlled changes (MOPM 1.9 / 1.10)

Change Control register/new entries now open the governed project owner instead of a creation placeholder. Users can start capability additions/changes, line-station/additional-location changes, procedure changes and regulatory/organization changes. Capability additions retain their 11 readiness gates. The other exposed change types receive five pending hard gates for scope/approval impact, safety assessment, controlled revisions, personnel/resources and Authority requirements. The source requirements remain fixed defaults; adding a project does not pass any gate. Scope/reason validation runs before storage, and the UI gives inline field feedback.

Quality self-evaluation, named Executive approval, Authority submission and Authority acceptance retain separate attributable decisions. Approved Authority submission/acceptance now requires selecting a retained Authority evidence asset belonging to the same AMO; disposed, general-category, foreign or missing assets cannot qualify. Decision snapshots preserve the selected asset/checksum. PostgreSQL gate updates lock the gate table explicitly, fixing an outer-join locking failure found by the real database probe. Generic create/update/delete/action routes for historical change-register records cannot bypass this owner; historical pending/implemented/rejected views remain read-only.

This is readiness and approval workflow coverage, not proof of actual implementation. Physical-address notice timing, operational implementation/conditions verification, post-implementation review, and the content of each submitted assessment still require further governed handling and validation. Existing source references marked verified are accountable attestations; a string reference alone is not independent verification of an external approval document. Existing projects are not silently rewritten or approved.

| MOPM content | Portal owner / handling |
| --- | --- |
| Organization, responsibilities, appointments and access | Tenant accounts, workforce authorizations and Quality roles. Tenant administrators inherit operational entry/capability gates; tenant boundaries, independence and domain evidence checks remain enforced. |
| 1.6 manpower, duty and rest | Rostering validator now applies planned 12-hour duty, actual 16-hour maximum, 11-hour shift rest and rolling 72-hour / 7-day limits without requiring optional seeded tenant rules. Existing protected 24-hour rest and stricter rules remain. Actual extensions over 12 hours generate a documented-review warning. |
| 2.1–2.7 suppliers, incoming components, storage and tools | Procurement supplier scopes, incoming inspection, inventory, custody and equipment/calibration workspaces. Calibration evidence uses the post-scrapping retention class. |
| 2.8 maintenance data | DMS publication/revision control and exact controlled-data links in work orders. Current published data is rechecked before contracted work transitions. |
| 2.9–2.13 repairs, AMP, MCAI and work-card completion | Technical Records, planning, airworthiness publications/compliance actions, work orders and task cards. The blanket technical-record setting now defaults to 3 years and cannot be set below 3; service-life classes are separately retained. |
| 2.14, 2.17, 4.3 record protection and operator copies | Shared retention catalogue, multi-class/event assessment, legal holds, immutable evidence/checksums, transfer and disposition controls described above. |
| 2.15–2.16 defects, certification and release | Defect/work-order/CRS owners retain certification authority. A provider account or administrator UI control does not itself issue a maintenance release. |
| 2.18, 2.24 occurrences, safety and human factors | Safety reports, investigations, risk/MOC, training and linked evidence. Investigation/SMS preservation obligations are captured in retention facts. |
| 2.19–2.23 external work | Provider qualification, agreements, technical orders, custody, controlled evidence, additional-work decisions and independent acceptance. |
| Part L2 line maintenance | Existing line-work, defect/MEL, technical-log, components and pooled/loan custody owners; do not substitute generic QMS registers for those transactions. |
| 3.1–3.3 assurance | Audit programme, findings, CAR/CAPA, effectiveness verification, management review and protected audit archives. |
| 3.4–3.12 training, competence, authorizations, exemptions and specialists | Training/workforce authorization owners; QMS independence and separately governed regulatory exemption controls remain. |
| 3.13 external-provider surveillance | Initial qualification, category policy, supplier scopes, audits/findings and annual review limit. |
| Part 4 operator interface | Operator/contract/work-order and DMS owners; original/copy handover obligations must retain delivery evidence and longer applicable record periods. |

The coverage map identifies system owners, not proof that every operational procedure has been exercised. Break recording, roster notice, night/early-start patterns, physical tool serviceability, actual operator handovers and every specialist release lifecycle still need their own operational validation; the added duty checks do not certify those activities. A reference field records accountable verification and is not automatic validation of a physical approval certificate or contract clause. This release does not fabricate those facts, sign releases, send invitations or dispose of business records during testing.

## Verification

Automated checks cover calendar anniversaries/leap years, longest applicable periods, multiple classes, unknown events, status-summary restrictions, extension floors, preservation obligations, legacy audit-package floors, both disposition-request route owners, contracted function/access gates, supplier-search SQL binding, administrator inheritance and adjacent-roster duty/rest calculations. Browser checks cover compact menus, 47 shared-register views, mobile geometry, settings changes, email entry and protected retention inputs. Live authenticated evidence and final release checks are recorded in `qms-workspace-review-2026-10-22.md`; ignored `.artifacts` contain captures and logs. Fixture tests are distinguished from live verification.
