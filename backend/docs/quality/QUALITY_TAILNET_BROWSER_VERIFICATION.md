# Quality Tailnet Browser Verification

This procedure runs the opt-in Playwright harness against a portal deployment that is reachable only from a Tailnet-connected workstation or self-hosted runner.

## Security rules

- Use a dedicated non-production AMO administrator or test auditor account.
- Do not put credentials, CAR tokens or live audit identifiers in source files, shell history, screenshots or GitHub comments.
- Set credentials only in the local process environment or an approved encrypted runner secret store.
- Use a disposable test audit before enabling mutation tests.
- Revoke or rotate the test CAR invitation after verification.

## Required environment

From `frontend/`:

```powershell
$env:E2E_BASE_URL = "https://james.tail05da5e.ts.net"
$env:E2E_LIVE_QUALITY = "1"
$env:E2E_AMO_CODE = "safarilink"
$env:E2E_AMO_ADMIN_EMAIL = "<dedicated-test-user>"
$env:E2E_AMO_ADMIN_PASSWORD = "<secret>"
$env:E2E_QUALITY_AUDIT_PATH = "/maintenance/safarilink/quality/audits/<test-audit-reference>"
$env:E2E_CAR_INVITE_URL = "https://james.tail05da5e.ts.net/car-invite?token=<test-token>"

npx playwright test tests/e2e/quality-tailnet-live.spec.ts --project=chromium
```

The read-only checks verify:

1. successful AMO login;
2. authoritative War room → Checklist → Findings → Report → CARs → Evidence → Closeout navigation;
3. absence of the degraded workflow blocker;
4. no horizontal overflow at a 1366×768 viewport;
5. one active public CAR response stage at normal browser zoom;
6. closed-CAR overdue/edit controls are not visible.

## Fillable PDF mutation check

Only on a disposable audit with a committed AcroForm PDF:

```powershell
$env:E2E_EXPECT_FILLABLE_PDF = "1"
$env:E2E_ALLOW_QUALITY_MUTATION = "1"

npx playwright test tests/e2e/quality-tailnet-live.spec.ts --project=chromium --grep "fillable checklist"
```

The test opens the portal PDF editor, fills the first available AcroForm control and saves the updated PDF through the authenticated checklist endpoint. After the run, manually download the saved checklist once and confirm that the entered value is retained before accepting the implementation.

## Evidence retained on failure

The opt-in suite retains a Playwright trace, screenshot and video on failure. Review these artifacts locally before sharing them because they can contain tenant names, audit references and CAR details.

## Cleanup

After testing, clear the environment variables, delete any temporary evidence files and revoke the test CAR invitation. Keep the pull request in draft until the browser run and PDF round trip pass.
