# QMS Frontend Architecture

This document reflects the Phase 2 QMS/platform hardening pass against the uploaded codebase. It records what exists, what changed, known gaps, and the next exact implementation tasks. It does not mark placeholder surfaces as complete workflows.


## Current structure

The frontend uses React/Vite with routing centralized in `src/router.tsx`. QMS rendering is centralized through `src/layouts/QmsShell.tsx` and `src/pages/qms/QmsCanonicalPage.tsx`.

## Phase 2 changes

- Platform superuser direct access to tenant QMS is blocked.
- `QmsCanonicalPage` exposes the required module tree and labels planned surfaces.
- The login page no longer displays inactive social login buttons.
- Dynamic login visual polish was added without adding unsupported social auth.

## Frontend rule

The frontend may hide unauthorized navigation, but backend APIs remain the source of authorization truth.

## Gap

Some legacy quality/training/manual pages still exist for compatibility. They should be migrated gradually into canonical QMS module children once their backend support is verified.
