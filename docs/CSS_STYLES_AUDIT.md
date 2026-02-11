# Frontend CSS Audit & UX Refresh (QMS / Maintenance Schedule)

## Why this audit was needed
The existing frontend had a few systemic issues that caused the interface to feel washed out and inconsistent across dark mode, light mode, and “system” mode:

1. **Theme state mismatch:** the app exposed a theme toggle but only persisted `dark`/`light` with no true system-follow mode.
2. **Color-scheme mismatch:** browser-native controls could render with dark form styles while the app showed light styling (and vice versa) due to static `color-scheme` defaults.
3. **QMS hardcoded light surfaces:** several QMS styles used fixed `#fff`/`#f8fafc`, reducing contrast quality in dark mode.
4. **Calendar UX underpowered:** events were basic cards without severity cues, source provenance, resource grouping, or practical operations metadata.

---

## What was implemented

### 1) Theme architecture upgrades
- Added full **three-mode theme behavior**: `dark`, `light`, `system`.
- Added a resolved runtime mode (`resolvedScheme`) so components and `body` always know final color context.
- Added system listener for `prefers-color-scheme` changes to auto-update while app is open.
- Persisted both mode and resolved scheme in body dataset:
  - `data-color-scheme-mode` (`dark` / `light` / `system`)
  - `data-color-scheme` (`dark` / `light`, resolved)

**Result:** consistent app + browser-native UI contrast and correct mode switching without manual reload.

### 2) Base CSS color-scheme normalization
- Updated root and body states so browser controls track the resolved app theme.
- Keeps both mode capability and explicit dark/light behavior where needed.

**Result:** dropdowns, inputs, scrollbars, and native controls no longer feel visually disconnected.

### 3) QMS token bridge + contrast cleanup
- Introduced a **QMS token bridge** using existing design tokens (`--surface`, `--text-primary`, `--accent-primary`) to reduce hardcoded colors.
- Replaced select hardcoded shadows/backgrounds with token-driven values.
- Corrected QMS shell/content surface to theme-aware backgrounds.

**Result:** better contrast parity between light and dark while preserving existing visual hierarchy.

### 4) Maintenance schedule redesign (interactive calendar)
The calendar page was rebuilt to support operations-grade interactions:

- **Auto-update strategy:** TanStack Query refetch now set to **60s** with `refetchOnWindowFocus`.
- **Source controls:** filter by `Internal`, `Outlook`, `Google`.
- **Resource grouping:** events grouped by date and by `resourceGroup` (team/hangar slot).
- **Severity coding:** `standard`, `priority`, `critical` visual styles.
- **Operational details in modal:** source, sync timestamp, assigned engineers, location, severity marker.
- **Summary dashboard tiles:** total events, critical count, last sync time.
- **Iconography:** Lucide icons added for scanability (calendar, clock, users, aircraft, refresh, severity).

**Result:** calendar now behaves like a planning board with traceability and quick triage context.

### 5) Data model enhancements for sync-aware front-end
Expanded `CalendarItem` to include:
- `source`
- `lastSyncedAt`
- `resourceGroup`
- `severity`

Also extended mock fallback data to emulate backend sync-hub payload shape.

**Result:** frontend is now ready for server-side sync metadata without schema rework later.

### 6) Text animation + interaction polish
- Added subtle animated gradient sweep for QMS page title.
- Added reduced-motion safeguards.
- Improved event hover states and interaction affordance.

**Result:** motion feels modern but remains respectful of accessibility preferences.

---

## UX/UI engineering rationale

### Visual consistency principles used
1. **Token-first color strategy** over ad-hoc hex values.
2. **Resolved theme semantics** (actual shown theme) rather than mode-only semantics.
3. **Contrast-aware surfaces** for cards, controls, overlays.
4. **Stateful components** (loading/syncing/severity) for operational clarity.

### Aviation/QMS-specific rationale
1. **Source provenance** is visible per event for audit readiness.
2. **Resource grouping** reveals bottlenecks (teams/hangar slots) quickly.
3. **Priority emphasis** supports safer dispatch and shift handoff decisions.
4. **Sync stamp visibility** builds trust in operational data freshness.

---

## Follow-up recommendations (next iteration)
1. Add drag/drop rescheduling with conflict validation.
2. Add capacity bars per resource group (slots utilized vs available).
3. Add SLA countdown badges for priority/critical jobs.
4. Add keyboard shortcuts for rapid calendar triage.
5. Add visual regression snapshots for light/dark/system + reduced-motion variants.

