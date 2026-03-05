# Shared Loading System (Phase 3.4)

AMO PORTAL includes a shared loading subsystem reusable by all modules.

## Architecture

Reused frontend platform patterns:
- app-root provider mounting in `App.tsx`
- route lazy-loading fallback in `router.tsx`
- module page-level async wiring through shared hooks/services

Shared primitives:
- `GlobalLoadingProvider`
- `useGlobalLoading`, `useScopedLoading`
- `useAsyncWithLoader`
- `GlobalLoaderOverlay`
- `InstrumentLoader` (core animated primitive)
- `PageLoader`, `SectionLoader`, `InlineLoader`, `ProgressLoader`
- `ProgressTrack`
- `SkeletonBlock`, `SkeletonCard`, `SkeletonTable`

## Instrument loader visual language

`InstrumentLoader` is the platform identity for loading states:
- encircled avionics-style frame
- orbiting ring segment
- central bounded sweep bar (activity/fill motion)
- waypoint pulse markers

This indicates activity/state only; it does not imply fake completion.

## Escalation rules (anti-freeze)

Centralized thresholds in `escalationRules.js`:
- Immediate (`0ms`): initiating control should show inline feedback.
- Short (`>=250ms`): show minimal loader signal (dock/inline context).
- Medium (`>=700ms`): escalate to section-level presentation for panel operations.
- Long (`>=2500ms`): allow overlay for blocking/high-impact operations.
- Very long (`>=9000ms`): show long-wait hint: “Taking longer than usual. Please keep this tab open.”

Modules should use `pickLoaderPresentation(task, elapsedMs)` indirectly through the shared overlay/dock to keep behavior consistent.

## Gallery route for visual validation

Internal-only route for manual QA (non-Playwright):
- `/ui/loader`
- `/maintenance/:amoCode/admin/ui/loader`

Access control:
- admin only
- hidden in production unless `VITE_ENABLE_LOADER_GALLERY=1`

Use this page to validate size/tone variants, compact mode, overlay/dock demos, and reduced-motion simulation.

## Scope + cleanup rules

- Tasks include route-affect flags, mode preference, timestamps, and persistence metadata.
- On route change, non-persistent tasks are cleared to prevent stale/spinning UI state.
- Always wrap async actions in `useAsyncWithLoader` or explicitly start/update/stop tasks.

## Reduced motion + accessibility

- `aria-live` and `aria-busy` are used on status containers.
- Loader animations are CSS-first and lightweight.
- `prefers-reduced-motion: reduce` disables continuous orbit/sweep/waypoint animation and falls back to static clarified indicators.
- Minimum-visible timing is retained to avoid flicker.

## CSS customization contract

The loader uses CSS custom properties:
- `--loader-size`
- `--loader-accent`
- `--loader-track`
- `--loader-speed`
- `--loader-glow`
- `--loader-radius`

Future modules/themes can tune these tokens without replacing loader behavior.

## Troubleshooting

If a page appears frozen:
1. Ensure the operation is wrapped in `useAsyncWithLoader`.
2. Use a stable `scope` and accurate `mode_preference` (`inline`, `section`, `page`, `overlay`, `auto`).
3. Confirm stop/cleanup runs on success, failure, cancel, and unmount.


## Contrast and sunlight readability (Phase 3.5)

Loader surfaces now use explicit readability tokens instead of opacity-only text tones:
- `--loader-text-primary`
- `--loader-text-secondary`
- `--loader-text-muted`
- `--loader-surface`
- `--loader-surface-border`
- `--loader-badge-bg`
- `--loader-badge-text`
- `--loader-shadow`

`InstrumentLoader` supports `contrast="normal"|"high"`.

Behavior:
- High contrast is forced when `prefers-contrast: more` is active.
- High contrast is forced when `forced-colors: active` is active.
- High contrast can be manually applied through `.amo-contrast-high` (used in gallery testing).

Guidance:
- Use `contrast="high"` for public verification and outdoor/mobile critical flows.
- Do not use opacity-only text values for critical status lines (title/subtitle/phase/status).
