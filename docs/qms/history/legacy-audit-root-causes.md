# Audit Assurance — traced root causes (contracts pass)

Tenant: **safarilink** · Audit: **QAR/MO/26/001** (`6bde5e00-0381-4d97-8196-6f5e39021680`) · Finding: **QAR/MO/26/001-F-001**.  
Do not commit until accepted.

## 1) Live HTTP 500 toast

| | |
| --- | --- |
| **Class** | **BACKEND ROUTING** (toast amplified by mutation error bridge) |
| **Trace** | `LiveAuditWorkspace` → `listChecklistExecutionGovernance` (GET) **200 empty**; parallel `heartbeatAuditPresence` (POST `.../presence/heartbeat`) **500** |
| **Root cause** | Audit presence routes were registered on the canonical Quality router but **not promoted ahead of** `/{module_path:path}`. Catch-all handled GET as a generic audits module view; POST heartbeat returned Internal Server Error. Checklist emptiness is a separate **PREREQUISITE** (0 bindings / 0 items; authoritative stage still Prepare). |
| **Smallest fix** | Promote presence routes before catch-all (`audit_presence_route_order.py`). Silence `/presence/heartbeat` in `portalFetchErrorBridge` so background beacons never toast. |
| **Fixed?** | **Yes** (route order + silent toast). Live verified: no 500 toast; presence shows auditor; checklist remains legitimately empty until Prepare applies a checklist. |

## 2) Findings continuity (Live F-001 vs Needs Review 0)

| | |
| --- | --- |
| **Class** | **FILTER** (not backend omit; not frontend stage mapping bug) |
| **Trace** | Live `GET /quality/audits/{id}/findings` → F-001 with `closed_at` set. Register `GET /quality/audits/register/paged?workflow_stage=needs_review` → `total=0`. Same API without stage → includes F-001. `workflow_stage=closed` → F-001 present. |
| **Root cause** | `needs_review` requires `closed_at IS NULL` (and no non-DRAFT CAR). F-001 is **closed** (`closed_at=2026-07-05…`). Live panel listed the finding without a Closed marker → dual-truth UX. |
| **Contract** | Backend does **not** omit the finding; Closed stage is the correct register bucket. |
| **Fixed?** | **Yes (UX label)** — Live findings list appends `· Closed` when `closed_at` is set. Register filter left as-is (correct). |

## 3) Prepare readiness 100% with 0 of 0

| | |
| --- | --- |
| **Class** | **FRONTEND STATE** |
| **Trace** | `AuditPrepareWorkspace` readiness: `percent: total ? Math.round(...) : 100` |
| **Root cause** | Zero required (non-waived) document requests treated as full readiness. |
| **Smallest fix** | When `total === 0`, show **N/A** / **0 required · Not started**; do not warn on “&lt; 100%”; warn that readiness is undefined until requests exist. |
| **Fixed?** | **Yes** — Prepare live shows `N/A` + `0 required · Not started`. |

## Commands / evidence

- Live probe (browser session): checklist-execution-governance **200** `items:[]`; presence heartbeat was **500** pre-fix; register needs_review **0**; unfiltered register includes F-001; closed stage includes F-001.
- `pytest amodb/apps/quality/tests/test_audit_presence_route_order.py` (+ setup route order) — **2 passed**
- `vitest` portalFetchErrorBridge + findingLifecycle — **9 passed**
