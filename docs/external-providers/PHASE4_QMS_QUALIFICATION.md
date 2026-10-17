# Phase 4 — QMS Provider Qualification, Approval and Surveillance

**Branch:** codex/external-provider-platform-20261009. **Pull request:** #560 (single draft PR). No Phase 5 work.

## Canonical ownership

- Procurement suppliers and their approval scopes remain the identity and authorized transaction master.
- Existing weighted supplier-evaluation templates, criteria, reviews and decisions remain the independent qualification-scoring system. Phase 4 category policy references an active evaluation template; it does not duplicate evaluation scores.
- Existing QMS audit occurrences, audit notices/guest acknowledgments, checklists, objective evidence, findings, CAR/CAPA control milestones, closure and effectiveness reviews remain authoritative. Phase 4 links audit UUIDs and does not create shadow audits or CARs.
- Existing Quality provider contracts, verified source evidence, regulated certificates and DMS manual revisions remain the source of contractual and documentary authority.
- Additive Phase 4 tables contain tenant- and supplier-qualified policies, qualification cases, check verifications, scope-level restrictions, surveillance links and immutable attributable events. PostgreSQL FORCE RLS protects the new rows. Migration extprov_261014_quality follows extprov_261012_partner.

## Controlled workflow

1. Register the provider using the canonical Procurement supplier. Proposed or imported suppliers are NOT automatically approved.
2. Quality Manager approves a tenant/category policy with questionnaire, mandatory baseline checklist, active scoring template, approved manual references, whether an initial QMS audit is required, the applicable Safety/Authority approval gates and the surveillance interval. Annual audits are category-specific, not universal.
3. Quality Manager or Officer opens INITIAL, RENEWAL, REQUALIFICATION or REINSTATEMENT case, freezing the current approved policy version. The explicit Phase 2 grant profile.propose lets a prospective or restricted provider submit questionnaire answers; it does not grant procurement or Quality approvals.
4. Quality reviews objective evidence against the existing VERIFIED Quality provider evidence records (same tenant/supplier and current validity). Each checklist decision retains evidence/ref, expiry, actor and rationale. Alternative documented qualifying review must rely on verified QMS evidence.
5. Appointed Base/Line/Workshop Maintenance Manager accepts exact technical scope. Safety Manager documents SMS/MOC decision with reference; Quality Manager verifies a current Quality-verified regulatory certificate or documents NOT_REQUIRED only where category policy permits. Mandatory Safety/Authority gates cannot be waived.
6. Existing EXTERNAL/THIRD_PARTY QMS audit occurrence is linked without creating a new audit. Independence, signed notices, acknowledgment, checklist, evidence, findings, CAR release, escalation, acceptance and effectiveness stay in Live Audit and CAR controls.
7. Quality Manager final case decision requires current independently reviewed scored supplier evaluation, exact scoped technical owner approval, verified checks, required active contract, applicable audit and open-CAR gates and role separation. The canonical supplier decision service updates supplier status and activates evaluation-linked governed scopes; Phase 4 has no separate operational approval.
8. Quality Manager imposes bounded ORGANIZATION, SITE, CATEGORY, CAPABILITY, PRODUCT_FAMILY, FUNCTION and CONTRACT restrictions with reason, effective/expiry dates, affected references and CAR links. Procurement supplier-use gate denies matching or unproven-safe scope transactions, even on controlled overrides; original records remain untouched. Lifting requires Quality-approved REINSTATEMENT case plus closed linked CAR and effectiveness milestone where required.
9. Review deadlines and current QMS CAR status power surveillance alerts. Existing scheduled worker deduplicates notifications to tenant Quality Managers. Partner receives limited Quality notices in its Phase 3 inbox. Staff can record surveillance outcome and manual overdue escalation.
10. Existing QMS External Providers detail page includes qualification, category policy, scoped restrictions, technical/Safety/Authority reviews, QMS audit links, history and source-linked regulatory JSON export. Partner portal displays its own questionnaires and active restrictions and permits answers only.

## Governance separation

| Authority | Permitted Phase 4 action |
|---|---|
| Quality Manager | Configure policy; Quality decision; regulatory verification; impose/lift restrictions; surveillance conclusions; export |
| Quality Officer | Prepare case, independently verify documentary evidence, link existing audit; no final Quality approval |
| Maintenance Manager (Base/Line/Workshop) | Accept/reject technical capability and proposed scope |
| Safety Manager | Safety risk / MOC assessment decision with reference |
| Assigned auditor | Governed audit execution, subject to established QMS independence |
| Procurement | Commercial supplier master, purchasing only if Quality gate allows |
| Provider | Assigned questionnaire and evidence/CAR response; never self-approval |

## Draft Safarilink procedural trace; NOT approval evidence

Draft MOPM Issue 4 sections previously identified in the repository regulatory trace: §§1.11 (arrangements), 2.1 (supplier evaluation and surveillance), 2.2 (parts and material procurement), 2.20 (defective component dispatch), 2.23 (contracting and subcontracting), 3.13 (subcontractor Quality audits), and 5.2 (contractor register). Exact subclause wording and approved manual references must be verified against the controlled, Authority-approved manual. The **proposed Safarilink annual subcontractor audit** needs explicit tenant category-policy adoption with 365 surveillance days; it is NOT silently universal.

**Unresolved policy determinations:** mandatory vs substitutable initial audits by category; KCAA/State-of-Registry acceptance and validity requirements per contracted activity; foreign-state applicability; SMS/MOC threshold and source register; approved templates and pass scores; risk-adjusted surveillance periods; site, product and contract-specific technical classification; Quality signatory independence and source evidence; approved register/export format; approved contractual flow-down, consent and DMS release. No undocumented regulatory conclusion has been assumed.

## Verification boundary

Source-implemented only. As directed, no manual database upgrade/downgrade, unit tests, browser tests, typecheck, build, lint or CI execution. The real data lifecycle, completed migrations, tenant RLS, template/approval transitions, external email, mobile UI, antivirus/CDR, authoritative SMS reference, document distribution and exact workbook reconciliation must be accepted in Phase 10. Approved organization data changes still require canonical domain-owner application; partner qualification does not rewrite it. No Phase 5 code was started.
