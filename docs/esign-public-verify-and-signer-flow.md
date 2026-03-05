# E-Sign Public Verify and Signer Flow (Phase 3)

## Public verification page
Route: `/verify/:token`

Behavior:
- Invalid/expired/revoked tokens render generic not-found messaging.
- Valid tokens render non-leaky trust details returned by backend:
  - request title and signer summary
  - document + artifact fingerprints
  - `appearance_applied`
  - `cryptographic_signature_applied`
  - `storage_integrity_valid`
  - `signature_present`
  - `cryptographically_valid`
  - timestamp flags and last validation check

## Signer flow page
Route: `/maintenance/:amoCode/:department/esign/sign/:intentId`

Flow:
1. UI requests intent-scoped WebAuthn assertion options.
2. Browser-native passkey ceremony runs via `navigator.credentials.get`.
3. UI posts assertion to `verify-and-sign` endpoint.
4. Confirmation status is displayed without mislabeling assurance:
   - WebAuthn approval is intent evidence
   - artifact cryptographic status comes from backend/provider outcome

## Labeling safeguards
- UI avoids ambiguous "Signed" wording for appearance-only artifacts.
- UI never collapses storage integrity and cryptographic validation into one badge.
- UI does not expose tenant-internal ids or provider secrets on public verify pages.


## Phase 3.3 loading behavior
- Public verify route now shows a page loader ("Loading verification record") before resolving to valid / generic not-found / service error states.
- Signer flow now uses staged loading phases: preparing session, waiting for passkey, verifying approval, and finalizing artifact refresh.
- Loading states are powered by the shared global loading subsystem (`docs/shared-loading-system.md`) for reuse in other modules.


## Passkey-first signer UX (Phase 3.6)
- Signer page now checks internal authenticated passkey availability.
- If passkey exists: primary action is `Sign with passkey`.
- If no passkey exists: primary action is `Set up passkey to sign`, then flow continues automatically to signing after setup.
- Unsupported browser and insecure-context (HTTP) states show explicit guidance.
