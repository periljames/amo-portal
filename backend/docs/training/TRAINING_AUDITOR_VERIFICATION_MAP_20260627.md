# Training auditor verification map — 2026-06-27

## Fast secure option selected

Use internal time-boxed access codes first. This is the fastest secure path because it does not require an external SSO provider, SAML metadata, OIDC client setup, or auditor account onboarding.

Workflow:

1. AMO Quality/Training editor creates an auditor access grant.
2. Backend returns a verification URL and an access code once.
3. AMO gives the guest auditor the URL and code for the audit window.
4. Auditor opens the verification URL and enters the code.
5. Backend returns verified training profile evidence in HTML or JSON.

## Reuse rule

Auditor codes are reusable within the configured audit window. Default window is 8 hours. `max_uses` is optional; when null, the same code can be reused until expiry.

## Protected creation endpoint

```http
POST /training/auditor-access
```

Body:

```json
{
  "target_user_id": "USER_ID",
  "target_record_id": null,
  "expires_in_hours": 8,
  "max_uses": null,
  "auditor_name": "Guest Auditor",
  "audit_reference": "AUDIT-REF",
  "notes": "Optional context"
}
```

Response includes:

```json
{
  "verify_url": "/public/training/users/USER_ID/verify?format=html&amo=TENANT&token=...",
  "access_code": "ABCD-234567",
  "expires_at": "..."
}
```

Store or display `access_code` immediately. The raw code is not stored.

## Public verification endpoints

HTML/GET:

```http
GET /public/training/users/{user_id}/verify?format=html&amo={amo_code_or_slug}&token={token}&code={code}
```

JSON/POST:

```http
POST /public/training/users/{user_id}/verify
```

Body:

```json
{
  "amo": "TENANT_SLUG_OR_CODE",
  "token": "TOKEN_FROM_VERIFY_URL",
  "code": "ABCD-234567",
  "format": "json"
}
```

## Certificate QR route

Certificate QR codes now point to the public certificate verification route:

```text
/public/certificates/verify/{certificate_number}?format=html
```

Alias also exists:

```text
/public/training/certificates/verify/{certificate_number}?format=html
```
