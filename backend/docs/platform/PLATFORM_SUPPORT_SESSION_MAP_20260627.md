# Platform support session map — 2026-06-27

## Access model selected

Platform superusers can enter a tenant Quality surface only through an explicit support session.

Two access levels exist:

- `READ_ONLY` — platform superuser can start immediately with a reason. It allows dashboard, register, document, evidence, and other read/view routes only.
- `ADMIN` — platform superuser requests elevation. The session remains `PENDING` until an AMO-side approver approves it. It remains active only for the current time-boxed session and can be ended by either side.

Default expiry is 8 hours. The backend clamps requested expiry to 1–12 hours.

## Platform-side endpoints

Create read-only or request admin elevation:

```http
POST /platform/tenants/{tenant_id}/support-sessions
```

Body:

```json
{
  "access_level": "READ_ONLY",
  "reason": "Troubleshooting audit dashboard issue",
  "expires_in_hours": 8,
  "ticket_reference": "SUP-123",
  "requested_route": "/api/maintenance/safarilink/quality/dashboard"
}
```

List sessions:

```http
GET /platform/support-sessions?tenant_id={tenant_id}&status=ACTIVE
```

Get current active platform sessions:

```http
GET /platform/support-sessions/current
```

End own platform support session:

```http
POST /platform/support-sessions/{session_id}/end
```

## Tenant-side approval endpoints

List pending admin-elevation requests:

```http
GET /accounts/admin/support-sessions/pending
```

Approve admin elevation:

```http
POST /accounts/admin/support-sessions/{session_id}/approve
```

Deny admin elevation:

```http
POST /accounts/admin/support-sessions/{session_id}/deny
```

End an active support session from tenant side:

```http
POST /accounts/admin/support-sessions/{session_id}/end
```

Approvers are AMO Admins or Quality Managers. Platform superusers cannot approve their own tenant elevation.
