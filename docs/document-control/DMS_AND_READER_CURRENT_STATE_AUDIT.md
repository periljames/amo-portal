# Document Control and Universal Reader Current-State Audit

## Audit baseline

- Repository: `periljames/amo-portal`
- Audited base branch: `main`
- Exact base SHA: `a76844db011648a866cd1247c2d218aba85603d0`
- Audit date: 2026-08-06
- Canonical frontend workspace: `/maintenance/:amoCode/document-control`
- Canonical reader workspace: `/maintenance/:amoCode/publications/:manualId/rev/:revisionId/read`
- Canonical backend prefix: `/doc-control/workspace/t/{tenant_slug}`

This audit is based on runtime imports, router registration, models, service calls and rendered components. Pull-request descriptions were treated as claims to verify, not as proof.

## Pull-request disposition

| PR | State at baseline | Actual disposition |
|---|---|---|
| #468 | merged | Reader rendering and navigation fixes are in `main`. |
| #473 | merged | Reader stability refinements are in `main`. |
| #474 | merged | Latest reader stabilization is the current base. |
| #467 | open draft, non-mergeable | Obsolete base; do not stack new work on it. |
| #469 | open draft, non-mergeable | Obsolete base; superseded by merged reader work. |
| #358, #367, #368, #369 | merged historical DMS slices | Established much of the lifecycle, publication, knowledge and record architecture now present. |
| #376, #378, #389, #425, #433, #447 | merged historical hardening/UX slices | Relevant history, but functionality was verified in current code rather than inferred from descriptions. |

## Runtime route map

| User route | Rendered component | Backend surface |
|---|---|---|
| `/maintenance/:amoCode/document-control` | `DocumentGovernanceDashboardPage` in this branch; previously `DocumentControlDashboardPage` | `GET /doc-control/workspace/t/{tenant}/governance/dashboard` |
| `/maintenance/:amoCode/document-control/library` | `DocumentGovernanceLibraryPage` in this branch; previously `DocumentControlLibraryPage` | `GET /doc-control/workspace/t/{tenant}/governance/library` |
| `/maintenance/:amoCode/document-control/library/:docId` | `DocumentControlRecordEntryPage` → controller governance detail or reader redirect | `GET /doc-control/workspace/t/{tenant}/documents/{manual_id}/governance`; ordinary reader still resolves an immutable read target |
| `/maintenance/:amoCode/document-control/structure` | `DocumentControlStructurePage` | Existing knowledge tree and reconciliation routes |
| `/maintenance/:amoCode/document-control/records` | `DocumentControlRecordsPage` | Existing generated-record routes |
| `/maintenance/:amoCode/publications/:manualId/rev/:revisionId/read` | Publications reader / `PdfReaderCoreV3` path | Existing reader bootstrap, source and progress routes |

## Capability matrix

| Capability | Current backend implementation at base | Current frontend implementation at base | Database model/data source | Permission rule | Test coverage at base | Status at base | Correction in this branch |
|---|---|---|---|---|---|---|---|
| Document identity | `manuals` and workspace serializers | Library and lifecycle detail | `Manual`, `DocumentControlProfile` | Tenant resolution plus profile access | Existing workspace tests | Partially wired | Governance aggregate keeps canonical `Manual.id` and exposes identity with governance completeness. |
| Immutable revision identity | Revision source path, checksum, status and immutable lock exist | Reader opens a specific revision | `ManualRevision` | Readable-revision resolution | Reader tests | Complete for PDF publication path | Checksum is promoted into all locations and annotations; missing checksum is actionable. |
| Granular ownership | Legacy profile has one owner user/department plus `Manual.owner_role` | Legacy overview shows ambiguous ownership | `DocumentControlProfile`, `Manual` | Controller writes; reader profile access | Profile tenancy tests | Unsafe/insufficient | Add normalized effective-dated `DocumentResponsibilityAssignment` with source, confidence, confirmation and history. |
| Controlled hierarchy | Knowledge hierarchy, move validation and stable node identity exist | Structure workspace exists | `DocumentationNode` | Controller mutation; filtered reader tree | Knowledge regression tests | Partially wired | Governance detail shows parent, path and children; backfill reconciles once per run. |
| Detected references | Checksum-keyed indexing and `DocumentationReference` exist | Reference monitor/knowledge UI is separate from document detail | `DocumentationReference`, `DocumentationIndexJob` | Controller resolution; reader source access filtered | Knowledge regression tests | Backend only/fragmented | Aggregate detections, jobs and exact source links into document detail. |
| Generic governed relationships | Limited reference relationship vocabulary | No coherent grouped related-items panel | `DocumentationReference` | Controller resolves | Limited | Missing | Add typed `DocumentGovernedRelationship` without replacing existing reference occurrences. |
| Forms and generated records | Execution profiles and immutable generated records exist | Records workspace exists | `DocumentationExecutionProfile`, `DocumentationRecord` | Controlled execution and custody checks | Existing record contract tests | Partially wired | Relationships can explicitly state `HAS_FORM`, `GENERATES_RECORD`, etc.; detail groups them. |
| Regulation links | Manual requirement links exist in manuals domain | Not aggregated in document detail | `RegulationCatalog`, `RegulationRequirement`, `ManualRequirementLink` | Tenant/authority rules vary | Existing manuals tests | Backend only | Generic relationship target supports regulation entities; canonical catalog integration remains a later adapter. |
| Document annotations | Reader progress/bookmarks exist; no format-neutral governed annotation model | No persistent governed highlight/evidence tray | `ManualReaderProgress` only | User-specific | Reader progress tests | Missing | Add checksum-bound canonical locations and annotations; capture UI integration remains pending. |
| Backfill | Hierarchy reconcile and revision reindex exist individually | No governed reconciliation control | Knowledge services/jobs | Controller only | Reconcile/reindex tests | Partially wired | Add idempotent run/items, dry run, selected documents, resume, retry and reconciliation evidence. |
| Library scalability | Existing corrected workspace library access-filters before pagination but offers limited filters | Existing table is bounded but lacks governance columns | `Manual`, profile, revisions | Access filtered | Workspace library tests | Partially wired | Add URL-backed governance filters, stable sort, page sizes 25–250 and sticky bounded table. |
| Dashboard actionability | Existing dashboard covers lifecycle workload | Mostly lifecycle KPIs | Lifecycle tables | Controller | Existing dashboard tests | Partially wired | Add work queues for unresolved ownership/relationships, failed indexing, orphaned structure and superseded references. |
| Reader TOC/zoom stability | One-shot navigation, physical page authority and virtualized rendering are in merged reader work | `PdfReaderCoreV3` | Reader state/progress | Revision read access | `publications-reader-stability.spec.ts` | Implemented but exact-head revalidation required | Do not create a parallel engine. Retain existing reader and add governed entry/deep links. |
| Reader mode | Existing reader-mode enter/exit and `Esc` test | Implemented | UI state | Reader access | Existing Playwright | Implemented but exact-head revalidation required | No architecture change. |
| Audit mode | No complete evidence tray integrated with canonical annotations | Fragmentary audit links | QMS/audit models plus reader | Audit permissions | No complete E2E | Missing | Target architecture defined; not claimed complete in this PR. |
| Compare mode | Revision diff data exists; complete synchronized immutable viewer not demonstrated | Separate diff page exists | `RevisionDiffIndex`, revisions | Publication access | Partial | Partially wired | Target architecture defined; not claimed complete in this PR. |
| Cross-format adapters | DOCX/PDF source types exist; viewer ecosystem includes some format libraries | No common adapter contract demonstrated | Source revision fields | Format-neutral auth at document level | No complete adapter matrix | Missing | Target adapter interface documented; implementation is not claimed complete here. |
| Sharing | Reader supports authenticated deep-link behavior | Copy-link reader control exists | Revision/location URL | Auth and tenant access | Reader Playwright | Partially wired | Canonical `DocumentLocation` supplies durable provenance; policy is documented. |
| Telemetry | Reader and indexing have some logs/jobs | No consolidated privacy-safe operational metrics | Jobs/logs | Operational access | Partial | Partially wired | Event catalogue and privacy exclusions documented; full telemetry instrumentation remains pending. |

## Dead or duplicate implementation risks

1. `DocumentControlProfile.owner_department` and `owner_user_id` cannot represent business owner, controller, reviewers, approver, custodian and retention owner. They remain compatibility inputs only.
2. `DocumentationReference` is an exact extracted occurrence, not a universal relation table. Expanding it to audits, findings, training and work orders would overload its purpose.
3. The old controller detail page aggregates lifecycle entities but does not aggregate knowledge, hierarchy, indexing or granular responsibility. It remains in the tree for compatibility but is no longer the canonical controller detail export in this branch.
4. Open draft reader PRs #467 and #469 are stale and must not be merged or used as a base.
5. Reader work must continue through the current `PdfReaderCoreV3` path. A second reader engine would reintroduce source duplication and navigation authority conflicts.

## Risk classification

| Risk | Severity | Basis | Branch response |
|---|---|---|---|
| Ambiguous ownership permits unclear accountability | High | One legacy owner string/user cannot express governed roles | Normalized effective-dated assignments and unresolved warnings. |
| Inference could overwrite human governance | Critical | Automated detection is not approval | Confirmed values outrank inference; inferred/imported writes cannot be immediately authoritative. |
| Cross-tenant assignee or target selection | Critical | IDs are supplied by clients | Every assignment, document and target manual is tenant-validated server-side. |
| Exact evidence could drift between revisions | Critical | Page/quote alone is not immutable identity | Locations and annotations require source checksum plus revision ID. |
| Backfill could duplicate or overwrite records | High | Existing tenants have mixed metadata quality | Tenant-scoped idempotency key, item ledger, dry run, resume and confirmed-value protection. |
| Reader regressions after unrelated UI changes | High | Fit/zoom/virtualizer behavior is sensitive | Existing authenticated reader suite remains a merge gate; this branch does not replace the engine. |
| Apparent success when CI creates no jobs | High | A green PR UI without executed jobs is not evidence | PR must report zero-job runs as infrastructure failure. |

## Audit conclusion

The base contains a substantial controlled-publication lifecycle and a hardened PDF reader, but the document governance experience is fragmented. The key correction is not another reader rewrite. It is a normalized governance layer that joins canonical document/revision identity, effective responsibilities, hierarchy, extracted references, governed relationships, indexing and exact locations into one permission-checked aggregate and one actionable frontend workflow.
