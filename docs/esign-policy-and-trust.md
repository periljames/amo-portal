# E-Sign Policy and Trust (Phase 2.1)

## Policy levels
- `BASIC_APPROVAL`
- `APPEARANCE_ONLY_ALLOWED`
- `CRYPTO_REQUIRED`
- `CRYPTO_AND_TIMESTAMP_REQUIRED`

## Enforcement rules
- Request creation resolves effective policy (explicit request policy -> tenant active/default).
- Send/finalization may be blocked when provider health is required by policy.
- Crypto-required policies fail closed unless fallback is explicitly allowed by policy or explicit override.
- Timestamp-required policies fail if timestamp is missing unless explicit override `ACCEPT_NO_TIMESTAMP` exists.

## Achieved vs required assurance
- `achieved_level` is computed from actual output artifact.
- `policy_compliant` compares `achieved_level` to policy `minimum_level`.
- `finalized_with_fallback` + `downgrade_reason_code` record downgrade behavior and reason.

## Override model
Per-request explicit overrides (admin only):
- `ALLOW_FALLBACK`
- `BYPASS_PROVIDER_HEALTHCHECK`
- `ACCEPT_NO_TIMESTAMP`

Overrides are scoped, auditable, and never change labeling of actual achieved assurance.

## Revalidation policy
- If policy has `require_revalidation_on_verify=true`, verify can re-run cryptographic validation when stale beyond TTL.
- Validation source is tracked as `LIVE` vs `CACHED`.

## Critical semantic notes
- Appearance-only may be policy-compliant if policy allows it.
- Crypto-required policies can fail closed.
- WebAuthn approval, storage integrity, and cryptographic validation remain distinct evidence layers.
