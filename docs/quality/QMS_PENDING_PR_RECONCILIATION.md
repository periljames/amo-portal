# QMS Pending PR Reconciliation

Date: 2026-08-16  
Baseline: current `main` with merged #488 Assurance Operating System and merged #499 governed CAR/CAPA control loop.

No historical PR is to be merged wholesale into the live-audit implementation branch.

| PR | Current classification | Decision |
|---|---|---|
| #353 — Rebuild Quality war room and controlled checklist lifecycle | **SUPERSEDED / PARTIALLY_REUSABLE** | Open draft from the pre-#488 architecture. Preserve only any unique PDF/checklist interaction that current main demonstrably lacks. Do not merge its audit lifecycle/state model. Close as superseded after unique-delta review. |
| #280 — E-Signatures | **PARTIALLY_REUSABLE / REBASE_REQUIRED** | Highest-value historical source. Port WebAuthn/passkey signing intent, artifact hash binding, verification token/evidence bundle and provider abstraction onto current main. Do not reuse its old Alembic ancestry or merge the branch wholesale. |
| #40 — CAR invites and reminders | **SUPERSEDED / PARTIALLY_REUSABLE** | #499 now owns staged CAR/CAPA, reminders, deadline governance and escalation. Compare only guest/public invite UX or token behavior that current main still lacks; then close as superseded. |
| #290 — P0 compliance controls | **PARTIALLY_REUSABLE / REBASE_REQUIRED** | Current main already contains later QMS RLS and governed transition work. Review for unique capability-authz/ledger hardening only. Do not reintroduce stale tenant-normalization migrations wholesale. |

## Rules for selective porting

1. Start from current `main` only.
2. Diff the historical PR against current main before copying code.
3. Prefer current model names, tenant keys, permissions and Alembic ancestry.
4. Never replace #488 workflow state or #499 CAR control-loop state with historical equivalents.
5. Add focused tests for every selectively ported behavior.
6. Historical PR closure is deferred until unique-delta review is complete; this branch does not close them merely because they are old.

## Immediate reuse plan

- #280: inspect next, because same-day report approval/signing is a P0 requirement in the execution specification.
- #353: inspect only when implementing Live checklist/PDF ergonomics.
- #40: inspect when implementing external auditee access and CAR guest response.
- #290: inspect during external participant authorization and immutable event-ledger hardening.
