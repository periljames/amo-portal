# Audit workflow design review — 17 October 2026

This revision covers Setup, Prepare, Closing, Follow-up and Archive, while retaining the compact Fieldwork workspace. Backend files were not changed, and live verification did not submit audit forms or advance lifecycle stages.

## Changes

- **Shared navigation:** purposeful stage icons, numbered steps, visible selected/completed states and short descriptions. The current server stage remains distinct from the record being viewed. Mobile stage navigation scrolls within its own row. Repeated stage banners and duplicate navigation actions were removed.
- **Visual system:** warm surfaces, clearer spacing and quieter typography. Teal identifies planning/preparation, plum closing, amber corrective action and blue archive controls. Primary actions retain the selected tenant/accent theme. Status still includes text and icons. Dark warning/error colours use semantic tokens rather than hard-coded light-theme colours.
- **Setup:** a clear audit-definition header, numbered disclosure sections and calmer status treatments. Opening an existing audit now preserves its saved dates; it no longer silently moves past dates into the future and marks the definition unsaved. Explicit date-adjustment controls remain available.
- **Prepare:** readiness comes first, followed by the checklist, document requests and participant access. Planning, references, previous audit context, applicability and offline-file controls use native disclosures. The Offline files navigation link opens the correct disclosure, including hash navigation. Mandatory forms and readiness rules remain intact.
- **Closing:** the workspace now stays in normal page flow instead of covering the portal with an obsolete fixed viewport. Report narrative/meeting controls are available in a disclosure that retains unsaved inputs when toggled. The current closing step opens automatically; later/completed steps can be expanded for review. Existing permission, acknowledgement, signing and issue gates remain active. An empty sidebar column no longer consumes space.
- **Follow-up:** an actionable empty state explains where corrective actions come from and links to Fieldwork. Phone metrics use two columns rather than four full-width blocks.
- **Archive:** a coherent record/policy/control layout, readable dark-mode warnings and consistent form/action styling. Retention, legal-hold and disposition rules were not changed.
- **Loading and motion:** structured loading placeholders, short disclosure reveals and restrained hover movement. Reduced-motion preferences disable decorative animation. Theme changes do not animate a stage background independently of its text.

## Verification

Live checks use the existing dedicated verification account against the running local portal. They cover actual stage rendering, 390px layouts, light/dark switching, 44px stage links, keyboard disclosures, preserved local narrative input, saved Setup dates, Closing page positioning and sampled contrast/font weights. The narrative draft used by the test is never submitted.

Screenshots are retained in `.artifacts/workflow-design/`, including:

- `after-prepare-desktop.png`, `after-prepare-mobile.png`, `after-prepare-context-desktop.png`
- `after-setup-mobile-dark.png`
- `after-closing-desktop.png`, `after-closing-mobile-dark.png`
- `after-follow-up-desktop.png`, `after-archive-mobile-dark.png`

Archive exceeded the original 45-second loading wait on one pass, then rendered successfully on subsequent passes. That observation does not establish a backend root cause or certify archive-generation writes. The earlier checklist binding, mutation, sign-off receipt and independent-device synchronization work remains tracked in the [checklist review](checklist-workspace-review-2026-10-17.md).

Final results: 37 focused tests, the five authenticated live audit/DMS checks, and the expanded workflow pass at 320/390/768/1440px succeeded. The workflow pass also checks sampled dark-mode contrast of at least 4.5:1, heading/navigation weights no heavier than 500, and native closing-step expansion. The final production build, TypeScript check, 127-stylesheet CSS contract, modal-layer check and heavy-route chunk check passed. Build output is retained in `.artifacts/live-verification/workflow-build-verified.log`.
