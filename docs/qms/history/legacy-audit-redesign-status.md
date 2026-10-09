# Audit Assurance reconstruction — progress status

**Do not commit.** Live authority: Cursor Browser + evidence under `.runtime-logs/audit-assurance-redesign/`.

## Completed

### Phase 1 — Live inventory
- All major AA surfaces inspected at ~1400×906
- Inventory: `inventory/PHASE1_INVENTORY.md`
- Before screenshots: `screenshots/before/`

### Phase 3 — Contract seed
- `contracts/CONTRACT_TABLE.md` (seed; deeper Live/Findings root-cause agent in flight)

### Phase 4 — Wireframes
- Mid-fi pack: `wireframes/index.html` (served at `http://127.0.0.1:5179/` for review)
- Reviewed in Cursor Browser

### Slice 1 — Nav + geometry
- AA rail: Overview · Plan · Audits · Findings · Tools
- Plan hosts Programme|Calendar segment
- Assurance related pills demoted on AA surfaces
- Overview “Go to” strip removed
- In-progress CTA → **Continue audit**
- Live verified Overview + Audits CTA

### Slice 2 — Audits AG Grid register
- AG Grid Community register live
- Filters Mine/Upcoming/Active/Completed
- Client page of API bound ≤250; UI 25/50/100; URL sync
- Next actions: Continue audit / Follow up
- Live verified: `grid:true`, pagination, CTAs

## In progress / next

| Item | Status |
| --- | --- |
| Live 500 + Prepare 0/0→100% + Findings continuity root cause | Agent running |
| Slice 3 Setup/Prepare functional workbench | Next |
| Slice 4 Live workbench (no empty+500) | Blocked on Live 500 root cause |
| Slice 5 Closing/Follow-up/Archive | Pending |
| Slice 6 Findings & Actions AG Grid + continuity | Pending (default filter vs auto-OPEN CAR) |
| Slice 7–9 Plan/Planner/Evidence/Checklists | Pending |
| Full button matrix + acceptance matrix | After slices |
| P0 = 0 gate before commit | Not yet |

## Known P0/P1 (open)

1. **P0** Live stage HTTP 500 + empty checklist while authoritative stage Prepare
2. **P0** Findings register “Needs Review” empty while Live shows finding (likely auto-OPEN CAR → With auditee; product decision + fix)
3. **P1** Prepare readiness 100% on 0/0 required
4. **P1** Overview KPI wall / contradictory active programmes presentation
5. **P1** Audits API hard bound 250 without server page
6. **P1** Checklists Create template disabled while editor visible
7. **P1** Closing passkey interactive while fieldwork gate blocked
8. **P1** Full-page “Loading portal workspace…” flash on hard nav

## Tests so far (Slice 1–2)

- `check:css` — PASS
- `auditNextAction` + `auditsWorkspaceModel` Vitest — PASS
- Playwright live AA — SKIPPED (gate off) — not claimed as pass
