# Planning/Production Authenticated Screenshot Manifest

## Runtime context
- Date: 2026-03-03
- Tenant slug: `demo-amo`
- Runtime: PostgreSQL 16 + FastAPI backend + Vite frontend (authenticated session)

## Demo users used
- Planner: `planner@demo.example.com`
- Production: `production@demo.example.com`
- Quality: `quality@demo.example.com`
- Password: `ChangeMe123!`

## Authoritative seed path
- `python backend/scripts/seed_planning_production_auth_demo.py`

## Screenshot evidence
| File | Route | User | Proof |
|---|---|---|---|
| `planning-dashboard.png` | `/maintenance/demo-amo/planning/dashboard` | planner | Tenant-scoped planning dashboard with live cards and priority section. |
| `planning-utilisation.png` | `/maintenance/demo-amo/planning/utilisation-monitoring` | planner | Utilisation monitoring page loads in planning shell. |
| `planning-forecast.png` | `/maintenance/demo-amo/planning/forecast-due-list` | planner | Forecast/due list route resolves with operational table layout. |
| `planning-amp.png` | `/maintenance/demo-amo/planning/amp` | planner | AMP route resolves with planning module layout. |
| `planning-adsb.png` | `/maintenance/demo-amo/planning/ad-sb-eo-control` | planner | AD/SB/EO control page route verified. |
| `planning-work-packages.png` | `/maintenance/demo-amo/planning/work-packages` | planner | Work packages page resolves in tenant context. |
| `planning-work-orders.png` | `/maintenance/demo-amo/planning/work-orders` | planner | Planning work orders page resolves in tenant context. |
| `planning-watchlists.png` | `/maintenance/demo-amo/planning/watchlists` | planner | Watchlists page rendered while authenticated. |
| `planning-publication-review.png` | `/maintenance/demo-amo/planning/publication-review` | planner | Publication review queue page rendered while authenticated. |
| `planning-compliance-actions.png` | `/maintenance/demo-amo/planning/compliance-actions` | planner | Compliance actions gate page rendered while authenticated. |
| `production-dashboard.png` | `/maintenance/demo-amo/production/dashboard` | production | Production dashboard route with summary cards. |
| `production-control-board.png` | `/maintenance/demo-amo/production/control-board` | production | Production control board route resolved and rendered. |
| `production-work-order-execution.png` | `/maintenance/demo-amo/production/work-order-execution` | production | Work order execution page rendered in production context. |
| `production-findings.png` | `/maintenance/demo-amo/production/findings` | production | Findings/non-routines route resolved and rendered. |
| `production-release-prep.png` | `/maintenance/demo-amo/production/release-prep` | production | Release preparation page rendered with execution context. |
| `quality-dashboard-compliance-zone.png` | `/maintenance/demo-amo/quality` | quality | Quality cockpit route with compliance-aware priority surface. |

## Notes
- Screenshots were captured from authenticated tenant pages (not login screen captures).
- Browser artifacts were generated via Playwright tooling in this run.
