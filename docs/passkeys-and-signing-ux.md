# Passkeys and Signing UX (Phase 3.6)

## Discovery/reuse notes
- Reused existing guarded routing pattern in `frontend/src/router.tsx` (`RequireAuth`).
- Reused existing module entitlement gate via `ESignModuleGate` for passkey management/security page access.
- Reused shared loading system (`useAsyncWithLoader`, `InlineLoader`, `SectionLoader`, global escalation overlay).
- Reused existing E-Sign intent assertion endpoints for signing finalization.

## Account Settings → Security

Route:
- `/maintenance/:amoCode/:department/account/security`

Behavior:
- Shows a **Passkeys** card with:
  - Add passkey action
  - existing passkey list (masked credential id, created at, last used, transport)
  - remove passkey action with confirmation

API wiring:
- `POST /api/v1/esign/webauthn/registration/options`
- `POST /api/v1/esign/webauthn/registration/verify`
- `GET /api/v1/esign/webauthn/credentials`
- `DELETE /api/v1/esign/webauthn/credentials/{credential_id}`

## Sign with passkey flow

Route:
- `/maintenance/:amoCode/:department/esign/sign/:intentId`

Behavior:
- If active passkey exists: primary CTA = **Sign with passkey**.
- If no passkey exists: primary CTA = **Set up passkey to sign**.
- Successful setup automatically continues into passkey signing.
- Cancel/error states are explicit and non-destructive.

Signing API wiring:
- `POST /api/v1/esign/intents/{intent_id}/assertion/options`
- `POST /api/v1/esign/intents/{intent_id}/assertion/verify-and-sign`

## Secure context and browser support

- Passkeys require WebAuthn support and secure context.
- UI shows explicit messages for:
  - unsupported browser
  - insecure (non-HTTPS) context

## Wording safeguards

- “Passkey approval” is presented as an approval/authentication action.
- UI does **not** relabel passkey approval as cryptographic PDF signing.
- Final artifact trust semantics still come from backend verification/policy outcomes.

## Troubleshooting

If passkeys fail to prompt:
1. Verify HTTPS secure context.
2. Try a browser/device with passkey support.
3. Retry setup/sign action from the same signing session.
4. Ask tenant admin to confirm E-Sign module entitlement.
