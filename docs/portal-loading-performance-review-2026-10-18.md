> Recovery update, 19 October: the online cache-first request policy described below was reverted after a loading regression. See [recovery review](portal-runtime-recovery-2026-10-19.md) for the current behavior and visible server controls. Earlier measurements describe the previous run only.

# Portal loading and visual repair — 18 October 2026

## Verified causes and changes

- The shared URL `https://james.tail05da5e.ts.net` served `/@vite/client` and `/src/main.tsx`: the development runtime. It now serves the optimized, gzip-compressed bundle on the same port and URL. The API/worker processes were retained.
- A shared flex rule expanded the Assurance title into the available viewport height. Titles now keep their natural height. Live audit controls measured 10 px below the title.
- AG Grid supplied a white alternate-row background while QMS supplied pale text. Theme tokens now cover both row backgrounds, headers, borders, selection and hover across the portal's grid themes. Four live finding rows were checked in dark mode.
- Initial HTML had an empty root. A responsive themed boot skeleton now appears before the JavaScript entry executes. It was observed on the public URL with entry loading deliberately delayed.
- Shared route boundaries and Quality workflows now use structured skeletons. The auxiliary enhancement host no longer displays a second page loader. Ninety-five literal text-only loading panels in 73 files use one compact accessible placeholder while keeping their existing containers.
- Assurance intent preloading now targets the actual audit/register/scope/plan modules and includes button navigation. Existing page chrome remains around lazy content in the canonical assurance dispatcher.
- Operational JSON reads can reuse fresh, tenant/user-scoped device snapshots. API cache hits are checked before the six-request network queue, so cached screens do not wait behind slow background traffic. Expired records are not presented as fresh online responses. Forced-refresh, sensitive paths and live authority reads bypass cache-first behavior.
- Optional encrypted disk persistence no longer blocks a successful read from rendering. Memory is populated immediately; disk persistence continues independently.
- Successful domain writes, offline-sync completion and realtime updates invalidate cache-first reads. Presence, tokens and telemetry do not evict operational caches. Background mount refresh preserves existing query data.
- The service worker now returns content-hashed assets and versioned PDF.js assets directly from cache. It previously re-fetched even these immutable files on every navigation.
- Audit schedule text wraps and the grid height follows its row population.

## Verification

118 frontend tests passed across networking, queueing, account scope, live-authority exclusions, cache invalidation, service-worker caching, durable offline persistence, fieldwork projections and route preloading. The broader Quality suite also passed 156 tests (reported separately because suites overlap). The CSS contract passed for 129 stylesheets. Six runtime tests passed, including the selected shared/dev frontend modes. The optimized build runs TypeScript, modal-layer and heavy-route checks; its existing large-chunk advisory remains.

The public URL was verified to serve hashed production assets with gzip encoding and no development client. The inspected entry transferred about 273 KB compressed. A fresh browser authenticated through the frontend; a synthetic delayed-entry check captured the boot skeleton before the application started.

Public URL measurements with warm data/assets, 650 ms configured latency and 512 kbit/s download bandwidth:

| Check | Findings | Audits |
|---|---:|---:|
| Full reload to visible rows | 1.45 s | 1.58 s |
| Fully disconnected reload to visible rows | 1.33 s | 1.03 s |

All four findings and both audits remained visible. In-app clicks under the same throttle measured 1.49–2.43 s on this running workstation. These are measured warm-cache checks, not a promise that a first visit or an uncached dataset can load offline. Broad portal loading improvements share the same components and request/cache layer; live offline data checks here cover the two reported registers.

Artifacts are in `.artifacts/audit-workflow-run/`: `portal-live-serving.json`, `portal-visuals.json`, `portal-poor-network.json`, `portal-spa-network.json`, `portal-cold-boot.png`, and the build/test logs. Email actions were not performed.

## Shared launch

`npm run start:shared` builds and serves the optimized frontend on port 5173. The supervisor also accepts `--frontend-mode preview`; the Cursor environment uses that mode. Use `--frontend-mode dev` or `npm run dev` when HMR is needed. Frontend source edits require a rebuild to update the shared optimized URL. No backend application files were changed for this loading repair.

Final verification repeated the dark-row and title-spacing checks and slow/disconnected reloads against the rebuilt public URL. CSS, modal-layer, TypeScript/build and heavy-route checks passed. Document Control navigation and its page headings were also checked through the frontend. The transient login file was deleted.
