# Phase 9 — Full-stack requirement-to-source implementation matrix

**Scope:** phases 1–8 and Phase 9 consolidation on PR #560. **Assessment method:** static inspection of tracked sources, existing phase documents, route decorators, schemas, views and migration definitions. **No execution** of migrations, pytest, browser, typecheck, lint, build, GitHub CI or user acceptance; no certification is inferred. Original real register/contract-tracker workbooks are not available for format-specific validation.

### Matrix rules

**S** = identifiable code and data path exists, but *not runtime-verified*. **P** = partial integration or known correctness gap. **G** = specific implementation gap. **R** = responsibly reused canonical subsystem, interface integration may still need testing. **—** = not a distinct requirement for that workflow. Columns evaluate: **M** authoritative model, **DB** persistence, **Mig** migration, **Svc** backend logic, **API** route, **ACL** server permissions, **UI** front-end action, **Client** connected API call, **UX** loading/error/empty/success, **Links** cross-domain links, **Evt** events/notification, **Trail** retained history/evidence, **Doc** documentation. No S or R implies a passing test.

| Workflow | M | DB | Mig | Svc | API | ACL | UI | Client | UX | Links | Evt | Trail | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1. Canonical supplier & multiple provider roles | R | S | S | S | S | S | S | S | P | R | S | S | S |
| 2. Site, contacts, capabilities & approved scope mapping | R | S | S | S | S | S | S | S | P | S | P | S | S |
| 3. Legal/regulatory certificate verification & validity | R | S | S | S | S | S | S | S | P | S | P | S | S |
| 4. Controlled parent/subcontractor relationships & consent | R | S | S | S | S | S | S | S | P | S | P | S | S |
| 5. XLSX/XLSM staging, column mapping and duplicate control | S | S | S | S | S | S | S | S | S | R | P | S | S |
| 6. Import confirmation, source replay, supersession and guarded rollback | S | S | S | S | S | S | S | S | S | R | S | S | S |
| 7. Import history, bounded row review and reconciliation CSV | S | S | S | S | S | S | S | S | S | R | P | S | S |
| 8. External identity, email verification & recovery | S | S | S | S | S | S | S | S | P | S | S | S | S |
| 9. Vendor-key/email+password authentication and cookies | S | S | S | S | S | S | S | S | S | S | S | S | S |
| 10. MFA/TOTP/passkey and scoped session revoke | S | S | S | S | S | S | S | S | P | S | S | S | S |
| 11. Quality-managed vendor grant, activation and suspension | S | S | S | S | S | S | S | S | S | S | S | S | S |
| 12. Provider admin invite, membership and object-scope delegation | S | S | S | S | S | S | S | S | P | S | S | S | S |
| 13. Partner organization, change requests and decision review | S | S | S | S | S | S | S | S | S | P | P | S | S |
| 14. Partner evidence intake, malware scan and securely stored original | S | S | S | S | S | S | S | S | P | S | P | S | S |
| 15. Document requirements, acknowledgement and exact published DMS form | R | S | S | S | S | S | S | S | P | S | P | S | S |
| 16. QMS evidence verification vs intake acceptance, document retention | R | S | S | S | S | S | S | S | P | S | P | S | S |
| 17. Category-specific qualification policies, QMS decision guards | R | S | S | S | S | S | S | S | S | S | S | S | S |
| 18. Technical/Safety/Authority reviews and auditor independence | R | S | S | S | S | S | S | S | P | S | S | S | S |
| 19. Site/capability restrictions and reinstatement decisions | R | S | S | S | S | S | S | S | P | S | S | S | S |
| 20. Surveillance due/review and linked canonical QMS audits | R | S | S | S | S | S | S | S | P | S | P | S | S |
| 21. External QMS audit notices, document requests, finding/CAR/CAPA | R | R | R | R | R | R | S | S | P | S | **P** | S | S |
| 22. Agreement drafts, lifecycle & partner receipt (not signature) | R | S | S | S | S | S | S | S | P | S | P | S | S |
| 23. Contract signatures/renewal/replacement and independent authority | R | S | S | P | P | S | P | P | P | S | **G** | S | P |
| 24. RFQ invitation, question, quote, revision and technical alternatives | R | S | S | S | S | S | S | S | P | S | P | S | S |
| 25. PO issue, acknowledgements, shipments and proposals | R | S | S | S | S | S | S | S | P | S | S | S | S |
| 26. Actual receipt, inspection, Quality hold, return and warranty | R | S | R | S | S | S | S | S | P | S | **P** | S | S |
| 27. Technical contracted maintenance scope & approval gates | R | S | S | S | S | S | S | S | P | S | S | S | S |
| 28. Assigned member communications, job ETA and additional work | R | S | S | S | S | S | S | S | P | S | S | S | S |
| 29. Independent test evidence, release and technical closeout | R | S | S | S | S | S | S | S | P | P | **P** | S | S |
| 30. Safarilink property, tools, Stores custody reconciliation | R | S | S | P | P | S | P | P | P | **G** | P | S | P |
| 31. Provider lifecycle/contract/certificate expiry alert schedules | R | S | S | S | S | S | S | S | P | S | S | S | S |
| 32. Procurement/maintenance alert events & vendor recipient scoping | R | S | S | S | S | S | S | S | P | S | **P** | S | S |
| 33. QMS Audit/CAR/CAPA effectiveness/repeat alert adapters | R | R | R | **P** | R | R | R | R | P | S | **G** | S | P |
| 34. Tenant-owned reminder routing, thresholds, digest/quiet hours | S | S | S | S | S | S | S | S | P | S | S | S | S |
| 35. Resend accepted vs delivered/read event reconciliation | R | R | R | R | R | R | S | S | P | R | **P** | R | S |
| 36. Staff Quality 360, scopes, site/expiry calendar & register export | R | S | S | S | S | S | S | S | S | S | — | S | S |
| 37. Delivery/receiving/repair analytics and concentration indicators | R | R | S | S | S | S | S | S | S | R | — | R | S |
| 38. Human critical/sole-source classification with verified evidence | S | S | S | S | S | S | S | S | S | S | S | S | S |
| 39. Historical provider status/risk snapshot, immutable provenance | S | S | S | S | S | S | S | S | P | S | S | S | S |
| 40. Approval risk trends, repeat findings, CAR effectiveness, warranty outcomes | R | R | R | **P** | P | S | P | P | P | R | — | R | P |
| 41. Full tenant configurable retention/access controls | R | R | R | **P** | P | S | P | P | P | R | P | R | P |
| 42. Large export/background reprocessing, queue HA crash recovery | R | R | R | **G** | G | S | **G** | G | G | R | P | R | P |

### Authoritative source crosswalk

| Requirements | Canonical sources / proof of integration |
|---|---|
| 1–4 | \`procurement/models.py\`, \`provider_identity_router.py\`, \`quality/provider_governance_router.py\`, \`supplier_quality_control.py\`, \`ProviderIdentityPanel.tsx\` |
| 5–7 | \`provider_import_router.py\`, \`external_provider_import_batches/rows\`, \`ProviderImportPanel.tsx\`; source workbook-specific mapping remains unverified |
| 8–12 | \`external_auth_core.py\`, \`external_auth_router.py\`, \`external_passkey_router.py\`, \`external_tenant_grants\`, \`external_sessions\`, \`ExternalProviderPortalPage.tsx\` |
| 13–16 | \`external_partner_router.py\`, \`external_provider_documents_router.py\`, \`external_partner_evidence_submissions\`, \`quality_external_provider_evidence\`, existing DMS and provider document workspace |
| 17–21 | \`provider_qualification_router.py\`, \`quality_provider_qualification_*\`, original \`qms_audits\`, \`qms_audit_findings\`, \`quality_cars\`, \`qms_corrective_actions\` |
| 22–26 | \`quality_external_provider_contracts\`, \`external_procurement_router.py\`, \`procurement_events\`, \`procurement_purchase_orders\`, \`procurement_receipts\`, \`procurement_receiving_inspections\` |
| 27–30 | \`external_contracted_work_router.py\`, \`external_contracted_work_events\`, \`external_contracted_inspection_checks\`, existing Stores and controlled technical records |
| 31–35 | \`provider_alerts.py\`, \`provider_alerts_router.py\`, \`portal_scheduler_main.py\`, original \`qms_notifications\`, \`external_partner_notifications\`, \`email_logs\` |
| 36–40 | \`provider_oversight_router.py\`, \`provider_oversight_events.py\`, \`ProviderOversight.tsx\`, \`external_provider_oversight_snapshots\`, \`external_provider_special_classifications\` |

### Incomplete/not evidenced — not falsely closed

1. **Event coverage**: provider catalog is a vocabulary, not a guarantee of QMS notice/reschedule, CAR response/CAPA effectiveness/repeat finding, formal contract signature/renewal replacement, physical RMA/receiving/certification and every technical closure source hook. A corresponding authoritative transition/retry/receipt must be connected; never synthesize regulatory state.
2. **Stores and technical references**: custody journal and reference numbers do not, by themselves, update canonical movement ledger or satisfy foreign operator/Authority acceptance.
3. **Retention**: tenant-selectable form requirement, renewal, QMS/DMS metadata and retention class links exist; a universal, nonbypassable tenant-specific retention/disposal policy engine for *all* new records is not proven.
4. **Provider 360**: initial source aggregates now exist. Weighted risk trends, validated on-time denominator, repeated-finding common-cause classification and CAPA *effectiveness outcome* cannot be truthfully inferred from partial audit, receiving, warranty and PO records. No simulated scores are shown.
5. **Scale**: first 100–150 sites/scopes/contract/certificate rows per provider and first 100 calendar entries are intentionally bounded. Overlarge controlled CSV exports fail visibly; production background export with safe progress/recovery is still a source gap.
6. **Lifecycle provenance**: immutable decision snapshots start at Phase 9 deployment. Pre-existing event histories are preserved, not fabricated or rewritten into snapshots.
7. **Deployment**: migration graph, SQL portability, RLS, repeated worker behavior, signed provider webhook evidence, ClamAV/S3 HA, upload failure recovery, email domain/DKIM and actual browser behavior are **unverified**. No claim of green CI.
8. **Source trace**: Safarilink Issue 4 is a draft reference for tenant-specific procedures; actual adopted MOPM and statutory requirements need appointed post-holder approval. The original XLSX/XLSM supplier and contracts examples have not been reconciled against this source.

**Gate:** This matrix is an honest source-status ledger, not declaration that Phases 1–9 are accepted. See \`PHASE9_RISK_REGISTER.md\` and \`PHASE10_VERIFICATION_LEDGER.md\`.


### Late Phase 9 source remediation mapping (post-matrix review)

| Matrix row | Corrective source | Status after correction |
|---|---|---|
| 5–7: workbook staging/import reconciliation | ZIP expanded-size/parts/ratio, sheet/column/cell and scanned-row guards added to `provider_import_router.py`. Original per-tenant source reconciliation and parallel load remain unproven. | **S**, unexecuted |
| 36/38–39: portfolio, controlled register and Quality classification | Inactive/prospective lifecycle records retained in export/portfolio; verified evidence now checks `valid_from` and `valid_until` and tenant/provider; original Quality Manager decision remains authoritative. | **S**, unexecuted |
| 32/34: digest and alert delivery | Member digest opt-in applied to email; quiet-hour overlap cannot starve daily digest; source outbox `DELIVERED` clarified as handoff rather than inbox status. | **P**, signed-provider delivery/retry proof pending |
| 40: CAR effectiveness trends | Separate canonical `quality_car_milestones` outcomes now feed provider 360, including overdue, accepted, blocked and missing profile counts. Repeat-finding and warranty outcome trends remain incomplete. | **P**, remaining scopes explicitly open |
| 1/36: frontend register workflow | Stale tenant/search/filter/page responses are discarded during debounce and after navigation. | **S**, browser regression required |

This matrix retains its 42 original status rows and outstanding `P/G` cells. A source change is not a regulatory approval or a runtime PASS.
