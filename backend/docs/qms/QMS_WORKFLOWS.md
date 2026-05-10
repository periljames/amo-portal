# QMS Workflows

## Phase 3/4 workflow action coverage

The backend now supports tenant-scoped workflow action endpoints for the highest priority lifecycle actions.

## Audit lifecycle actions

```text
issue-notice
complete-fieldwork
generate-report
archive
```

Each action inserts a tenant-scoped workflow record and activity log entry.

## CAR/CAPA lifecycle actions

```text
submit-root-cause
submit-corrective-action
review
effectiveness-review
close
reject
```

The action endpoints prevent CAR closure through a bare frontend click. Closure and rejection must pass through the backend workflow route and activity logging path.

## Controlled document lifecycle actions

```text
versions
submit-approval
approve
publish
obsolete
```

The action endpoints insert approval/version/obsolete workflow records and update compatible parent document status values.

## Remaining workflow gaps

These routes are wired but still require richer dedicated UI and stricter domain validation:

- risk treatment workflows;
- change-control approval workflow;
- supplier periodic evaluation workflow;
- equipment out-of-tolerance workflow;
- management-review pack generation;
- immutable evidence package sealing.
