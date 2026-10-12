# Deferred verification obligations — Phase 10 only

1. Enumerate all Alembic heads after upstream merges; upgrade/downgrade against production-like PostgreSQL snapshots. Check composite FKs, unique constraints and reversible trigger removal.
2. Prove absent or mismatched `app.tenant_id` fails closed under FORCE RLS on every added table.
3. Confirm no cross-tenant contact/site/provider/contract/evidence/scope/guest user can be linked or queried.
4. Validate Quality supplier decisions and `assert_supplier_usage_allowed` for approval, hold, scope, expiry, suspended, revoked, and prospect states.
5. Verify descriptive metadata CRUD, stale version 409, validation and Quality-only consent/verification.
6. Verify real workbook supplier/contract mappings, XLSX/XLSM, formula strings, dates, missing values, invalid references, duplicates, concurrent uploads, dry-run, confirmation and CSV.
7. Verify idempotent fingerprint including mapping/sheet and controlled staging supersession/rollback. Ensure advanced Quality or operational records cannot be rolled back.
8. Verify frontend API integration, 403/409/422 messages, loading/edit/confirm buttons, focus and keyboard use.
9. Verify doc revision references and external account associations grant **zero** access until a later dedicated access phase.
10. Run deferred pytest, Vitest, Playwright, lint, typecheck, build and CI suites. Debug/repair defects in Phase 10, without weakening checks.
11. Reconcile with latest main and all related open PR changes before merge. Keep this PR draft until Phase 10.

## New verification obligations arising from PR #560 CI logs (12 October 2026)
12. Re-run clean PostgreSQL Alembic upgrade from the current graph and deployment upgrade on a pre-existing supplier schema. Confirm `external_import_pending_activation` is added exactly once and the downgrade never removes an earlier-bootstrap column. Verify the PG column ownership comment and alternate SQLite behavior where applicable.
13. Exercise creation and UPDATE/DELETE blocking for `external_provider_change_events` to validate the repaired PL/pgSQL immutable provenance trigger and its safe downgrade removal.
14. Exercise provider identity POST/PATCH for all nine resource kinds, including cross-tenant links, cross-supplier contacts, parent-provider contract consent, cycles and PATCH-only contract/consent changes; ensure no recursive calls or unvalidated references.
15. Verify that malicious formula-like source cells cannot become executable on reconciliation CSV export; verify edits can clear nullable fields and properly persist a site's `is_primary` flag.
16. Once tests are permitted, inspect the latest CI checks of PR #560, including the four migration-failed workflows from run IDs `37931784210`, `37931784254`, `37931784319`, `37931784300`; investigate any newly exposed failures instead of interpreting earlier blocked jobs as clean.
17. Inspect code and migration graph against intervening main/PR changes and reconcile the real vendor register and contracts tracker inputs. If either workbook is unavailable, keep source-specific reconciliation explicitly unverified.

18. Repeat the automatically failed migration path from runs `38210809633`, `38210809642`, and `38210809599`: assert PostgreSQL accepts both child and parent composite supplier foreign keys on `external_provider_relationships` without duplicate generated constraint names, and downgrade removes them cleanly.
19. Verify `PreparedSnapshotBroker` health refresh counts remain consistent with completed source callbacks at 100+ subscribers (original failing platform CI job `114684307638`) and failed worker callbacks preserve existing failure semantics. Do not relax the existing equality assertion.
20. Confirm tenant-authorized GET controls deny unprivileged access to provider administrative identity and import reconciliation records; confirm the frontend still reaches those endpoints for Procurement Officer, Stores Manager and Quality Manager.
21. Confirm blank header columns never bind to source mapping fields, and verify `SPECIALIZED_MAINTENANCE_PROVIDER` roles can be created and edited end-to-end without any implicit QMS approval.

22. For QMS Setup → Prepare job `114688119641`, verify the exact-heading Setup disclosures, saved definition, opening/closing custom schedules, actual notice draft+signed PDF, controlled manual transition sequence through ACKNOWLEDGED and PostgreSQL persistence. Assert the corrected test never relies on the parent-region locator within its own child or global inactivity waits.
23. Exercise multi-day audit windows whose end time is earlier than the start time on the clock but later in absolute date/time, including blur, re-fetch, and database persistence. Preserve existing tenant policy and ensure the end-date HTML control does not reject valid multi-day times.
24. Independently test real SMTP notice dispatch, auditee receipt, and auditee-identity-bound acknowledgment; an internal authorized operator's manual ACKNOWLEDGE transition does **not** establish an external auditee's actual acknowledgment. Confirm safeguards against forged acknowledgments.
25. Verify end-to-end DMS effective revision binding, immutable checklist item creation, external participant purpose-bound permissions, guest evidence upload/hash/retention and internal document-request acceptance after the new Setup test adjustments. Confirm all automatically triggered QMS/browser workstreams; do not infer green results from running or cancelled jobs.

26. Exercise governed document review API for four cases: REQUESTED without evidence → ACCEPTED must fail 409; UPLOADED with matching persisted tenant-scoped submission → ACCEPTED succeeds; REQUESTED with validated current controlled DMS exact revision → ACCEPTED may succeed; missing, wrong-tenant or stale revision evidence must fail. Repeat for REJECTED and optional-only WAIVED rules.
27. Confirm legacy `PATCH /audits/{id}/document-requests/{id}` rejects forged `status` and `file_ref` changes with 409 but still permits authorized non-governed descriptive updates. Inspect other direct writers and restore/retention paths to ensure no alternative bypass.
28. Complete browser submission journey with premature acceptance and legacy forgery assertions, genuine guest upload into `quality_audit_document_submissions`, linked sha256/file integrity and reviewed-by attribution. Do not weaken or skip existing PostgreSQL acceptance assertions.
