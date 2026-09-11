# Tenant administration and access

The role-access foundation is in commit `44178054e`. This follow-up consolidates tenant organisation management, setup navigation and administrator lifecycle enforcement. Backend policy is shared through `amodb.apps.accounts.tenant_authority`; frontend access and landing decisions use `utils/tenantAccess.ts` and `utils/roleAccess.ts`.

| Identity or appointment | Authority |
| --- | --- |
| Platform superuser | Platform control; can appoint permanent tenant administrators and revoke/deactivate administrators. Does not become a tenant operational user. |
| Standing tenant administrator | All tenant operational and administrative workflows, while active; no platform powers. |
| Delegated administrator | Same tenant authority during an activated authentication session, within the grant validity period. Direct appointment by an active tenant administrator or Accountable Executive can be temporary or permanent. |
| Self-requesting employee | Own administrator request waits for the tenant Accountable Executive; no self-approval. |
| Accountable Executive | Own operational role, approval of administrator requests, and administrator revocation/deactivation within the tenant. |
| Other managers and employees | Assigned operational profile, department, personal authorisations and governed workforce placement. |

Only the platform superuser or the same-tenant Accountable Executive may revoke an administrator appointment or deactivate an administrator. Enforcement covers user commands, legacy role removal, imports, import undo, and scheduled/executed offboarding. Revoking a platform-created grant removes its standing flag as well. Temporary authority is checked against the current authentication session; it is never cached as the person's underlying operational profile.

Personal inspection, certification and audit authorisations remain separate from job titles and administrator access. The supplied management brief and organisation chart inform role templates and reporting lines. Existing tenant-edited supporting profiles are preserved. Use **User Management → Structure & access → Reconcile framework** (or **Apply AMO/MRO framework** for an uninitialised tenant) to reconcile missing templates; assign named postholders through the governed workforce placement workflow. No named people or live tenant assignments are seeded by this change.

**AMO Management** edits only the current tenant's organisation/contact details. Its API accepts no tenant override, login-slug, activation or commercial-control fields. The old AMO profile URL redirects to this page. **AMO Assets & Setup** keeps bases, departments, personnel readiness and CRS release assets in one workflow; explicit stage links stay selected. Page state drives next/back navigation and readiness. The unused older profile and setup implementations have been removed.

The landing resolver prefers the person's current assigned department over stored browser context. A person with no accessible assignment lands on their own profile. Tenant URL mismatches return to the user's tenant. Administration, department workspaces and shared records/people navigation are grouped separately.

Validation covers backend policy and module role checks, frontend route/session tests, production compilation and browser workflow tests. Run the browser checks with `npx playwright test --config playwright.administration.config.ts` from `frontend`. These browser tests mock APIs; backend tests exercise disposable SQLite fixtures. They do not certify live tenant data, PostgreSQL concurrency/RLS, external delivery services, or deployment readiness for unrelated module features. Deployment and live tenant configuration are not performed by this change.

Verified locally: backend access/module regressions, 45 frontend unit checks, five browser workflow checks, production build (including modal and heavy-route checks), and the CSS contract. The governed Workforce PostgreSQL integration test was skipped because no PostgreSQL integration database was configured.

Follow-up review: AMO Management and User Management link directly to Workforce → Organization & roles for actual appointments (`section=workforce&workforce_view=governance`); access-profile editing remains a separate workflow. Administrator help text now reflects same-tenant Accountable Executive revocation authority. Groups and personnel search report retrieval failures with retry controls. The broader administrator-policy/Workforce rerun passed 78 tests; nine PostgreSQL-dependent integration tests were skipped. Tenant navigation/session unit rerun passed 23 tests.

Latest frontend verification: TypeScript build (`npx tsc -b`), all five mocked-API administration browser tests, and the CSS contract (127 stylesheets) passed. Browser coverage includes organisation saving, mobile release-asset navigation, foreign-tenant landing correction, appointment handoffs, and group-request failure feedback.
