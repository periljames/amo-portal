# Superuser Phase 4 Acceptance Contract

The delivery is accepted only when all of the following remain true:

1. The console exposes exactly two tenant environments: `REAL` and `DEMO`.
2. `ALL` is rejected by canonical frontend and backend APIs.
3. Tenant-scoped data never crosses the selected environment.
4. Tenant provisioning creates the AMO, initial administrator, departments, canonical subscription and module access as one controlled workflow.
5. Modules, plans, price books, price versions, subscriptions and entitlement overrides have one canonical relationship.
6. Runtime compatibility records are projections, not competing commercial sources of truth.
7. Invoices use structured line items and payment transactions determine balance and paid state.
8. Privileged user, tenant, subscription, security, integration and infrastructure actions retain an actor, reason and audit evidence.
9. Unsupported database failover is disabled rather than presented as functional.
10. Platform API activity extends valid sessions and a rejected request does not trigger a second manual logout.
11. Backend migration, SaaS control-plane contracts, frontend type checking, platform unit tests and production build must pass before merge.
