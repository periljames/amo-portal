# QMS Permission Matrix

This document reflects the Phase 2 QMS/platform hardening pass against the uploaded codebase. It records what exists, what changed, known gaps, and the next exact implementation tasks. It does not mark placeholder surfaces as complete workflows.


## Current route permission examples

| Surface | Permission |
| --- | --- |
| QMS cockpit | `qms.dashboard.view` |
| Inbox | `qms.inbox.view` |
| Calendar | `qms.calendar.view` |
| Audits | `qms.audit.view` |
| Audit create/update | `qms.audit.create` / `qms.audit.update` |
| Findings | `qms.finding.view` |
| Finding create | `qms.finding.create` |
| CAR register | `qms.car.view` |
| CAR issue/review/close | `qms.car.issue`, `qms.car.review`, `qms.car.close` |
| Documents | `qms.document.view` |
| Document publish | `qms.document.publish` |
| Training | `qms.training.view` |
| Training manage/export | `qms.training.manage`, `qms.training.export` |
| Reports | `qms.reports.view` |
| Reports export | `qms.reports.export` |
| Evidence | `qms.evidence.view` |
| Evidence download/archive | `qms.evidence.download`, `qms.evidence.archive` |
| Settings | `qms.settings.view`, `qms.settings.manage` |

## Role rule

`SUPERUSER` is deliberately excluded from tenant QMS wildcard permission. Use tenant roles such as `AMO_ADMIN`, `QUALITY_MANAGER`, `COMPLIANCE_MANAGER`, and module-specific roles inside each AMO.

## Gap

A normalized IAM permission table and tenant-specific role assignment matrix should be completed after the route/API consolidation stabilizes.
