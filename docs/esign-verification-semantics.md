# E-Sign Verification Semantics

## Three separate verification layers
1. **Approval evidence**
   - WebAuthn/passkey assertion verifies user presence/verification and intent binding.
2. **Storage integrity**
   - API recomputes SHA-256 of stored artifact bytes and compares with stored `signed_content_sha256`.
3. **Cryptographic PDF validation**
   - For provider-signed PDFs only, validates signature presence and provider validation outputs (chain/timestamp/revocation fields when available).

These layers are distinct and must not be collapsed into one boolean.

## Public verification response meanings
- `storage_integrity_valid`: artifact bytes match stored hash
- `signature_present`: cryptographic signature marker/presence result
- `cryptographically_valid`: provider cryptographic validation outcome
- `timestamp_present` / `timestamp_valid`
- `appearance_applied`
- `cryptographic_signature_applied`
- `cryptographic_validation_status`

## Example (appearance-only)
```json
{
  "valid": true,
  "storage_integrity_valid": true,
  "signature_present": false,
  "cryptographically_valid": false,
  "appearance_applied": true,
  "cryptographic_signature_applied": false,
  "cryptographic_validation_status": "NOT_RUN"
}
```

## Example (external cryptographic)
```json
{
  "valid": true,
  "storage_integrity_valid": true,
  "signature_present": true,
  "cryptographically_valid": true,
  "timestamp_present": true,
  "timestamp_valid": true,
  "appearance_applied": true,
  "cryptographic_signature_applied": true,
  "cryptographic_validation_status": "VALID"
}
```
