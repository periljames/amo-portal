# Reliability Canonical Replacement Validation

- Backend diagnostic run: `30806703800`
- Frontend diagnostic run: `30807212501`
- Publication diagnostic run: `30807925071`
- Source shell head: `476fc3a96a6cdefbd5bcb89dc01a25dbb3a96f7a`
- Publication run: `30808050534`
- UTC publication time: `2026-08-03T11:04:33Z`

## Architecture enforced

- one frontend route tree: `/maintenance/:amoCode/reliability/*`
- one backend API prefix: `/reliability/*`
- no `/reliability/v2` API, aliases, compatibility redirects or duplicate clients
- no generic department-home or legacy report-page interception
- controlled reports are integrated into the canonical Reliability workspace
- no tracked test database or Python cache artifacts

## Verified checks

- backend compilation, full application import and canonical route/freshness tests
- tenant-navigation regressions and CSS contract
- scoped ESLint on Reliability-owned routing and UI boundaries
- full TypeScript/Vite production build
- clean Git staging and local commit creation

## Current tenant-shell synchronization

- Synchronized shell head: `309a8eac0aecfdbb19a1ecd71c83cdbaababb074`
- Merge diagnostic run: `30808533950`
- Merge publication run: `30808850509`
- UTC merge time: `2026-08-03T11:16:12Z`
- The exact Git merge completed with zero conflicted files.
