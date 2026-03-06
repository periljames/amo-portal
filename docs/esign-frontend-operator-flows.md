# E-Sign Frontend Operator Flows (Phase 3)

## Discovery summary (reused patterns)
- Frontend uses React + React Router with protected routes wrapped by `RequireAuth` in `frontend/src/router.tsx`.
- Tenant context is path-scoped (`/maintenance/:amoCode/:department/...`) and auth context comes from `services/auth`.
- Module gating pattern is entitlement-driven (`billing/entitlements`) as used by existing module pages.
- Existing shared UI primitives were reused: `PageHeader`, `SectionCard`, and existing badge styles.

## Operator routes
- `/maintenance/:amoCode/:department/esign`
- `/maintenance/:amoCode/:department/esign/requests`
- `/maintenance/:amoCode/:department/esign/requests/new`
- `/maintenance/:amoCode/:department/esign/requests/:requestId`
- `/maintenance/:amoCode/:department/esign/requests/:requestId/evidence`
- `/maintenance/:amoCode/:department/esign/artifacts/:artifactId/validation`
- `/maintenance/:amoCode/:department/esign/provider` (admin)
- `/maintenance/:amoCode/:department/esign/reports/trust-summary` (admin)
- `/maintenance/:amoCode/:department/esign/requests/:requestId/overrides` (admin)

## Admin/operator safety controls surfaced in UI
- Provider readiness is shown separately from request trust state.
- Revalidate-now action is explicit and user-triggered.
- Override creation requires justification + explicit confirmation checkbox.
- Evidence bundle UI warns that exports are sanitized and exclude secrets.

## Trust semantics in UI copy
- "Approval recorded" is separate from PDF cryptographic signature state.
- "Storage integrity verified" is separate from cryptographic validation result.
- Appearance-only outcomes are explicitly not described as cryptographically signed.


## Phase 3.3 loading integration
- E-Sign artifact validation actions now use shared inline loaders for revalidate/regenerate/compare actions.
- Section-level loading (`SectionLoader`) is used when artifact validation, verify-link state, and access policy are fetched together.
- Loader labels remain truthful (e.g., "Revalidating artifact", "Comparing provided fingerprint") and do not imply completion/success before backend confirmation.
