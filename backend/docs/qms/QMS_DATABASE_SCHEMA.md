# QMS Database Schema

This document reflects the Phase 2 QMS/platform hardening pass against the uploaded codebase. It records what exists, what changed, known gaps, and the next exact implementation tasks. It does not mark placeholder surfaces as complete workflows.


## Current tenant key

The current application uses `amo_id` as the tenant key. The target architecture refers to `tenant_id`; in this codebase, `amo_id` is the current effective tenant identifier. A future migration may rename or alias this into a platform tenant model, but this phase avoids unsafe global renaming.

## Implemented / referenced QMS tables

The backend generic module router references these existing or expected tables:

- `qms_audits`
- `qms_audit_programs`
- `qms_audit_schedules`
- `qms_audit_team_members`
- `qms_audit_notices`
- `qms_audit_scopes`
- `qms_audit_war_room_files`
- `qms_audit_checklists`
- `qms_audit_evidence`
- `qms_audit_findings`
- `qms_audit_reports`
- `qms_audit_post_briefs`
- `qms_audit_archives`
- `quality_cars`
- `qms_documents`
- `qms_document_approvals`
- `qms_document_approval_letters`
- `qms_document_templates`
- `qms_document_obsolete_records`
- `qms_document_revisions`
- `qms_document_distributions`
- `qms_risks`
- `qms_risk_actions`
- `qms_suppliers`
- `qms_equipment`
- `qms_management_reviews`
- `qms_activity_logs`
- `qms_archive_packages`
- `qms_evidence_files`
- `qms_settings`

## Changed identity schema

`users.amo_id` is now nullable for global platform superusers. Tenant users should still have an `amo_id`.

## Gap

Not every table listed in the master prompt is fully implemented with a domain service and migration. Missing or partial tables should be introduced module by module with tenant-scoped tests.
