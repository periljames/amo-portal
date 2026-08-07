# Post-#477 Document Reader Consolidation Audit — 2026-08-07

## Baseline

PR #477 is merged and its merge commit is the baseline for this follow-on work. The merged branch itself did not receive additional commits after merge.

The overlapping live reader work was found in draft PR #481 (`agent/document-reader-realworld-stability`). That branch was created before #477 merged and had diverged materially from current `main`, so it is not a safe merge source as a whole.

## Concurrent-agent work reviewed

### Accepted and replayed on current `main`

1. **Stale navigation release in `PdfReaderCoreV5`.** Manual wheel, touch or pointer interaction inside the virtual PDF viewport releases consumed programmatic navigation so an old page request cannot keep snapping the reader back after the user takes control.
2. **Zoom-settle handling.** Pending navigation is cleared while scale geometry changes and the physically active page is re-established after the short settle interval. Manual interaction cancels the pending settle request.
3. **Reader hash cleanup.** Consumed `#pdf-page-N` hashes are cleared so stale hash navigation cannot replay after geometry changes.
4. **Assisted-navigation awareness of the V3/V4 virtual viewport.** Page targeting now recognizes `.pdfv3-page` and scrolls the reader's own viewport before falling back to outer application scrolling.
5. **Route-scoped scroll anchoring and watermark scaling.** Browser scroll anchoring is disabled inside the virtual PDF surface and the uncontrolled watermark scales from the PDF page container.
6. **Dense chrome tuning without changing ownership.** Existing React-owned header, tabs and controls are retained and compacted; no duplicate control surface is introduced.

### Rejected from the concurrent branch

The proposed `PublicationReaderChromeBridge` was not carried forward. It located live UI nodes with `document.querySelector`, used `createPortal` to duplicate publication tabs and the assistant entry point, retried DOM discovery through animation frames, and synthetically clicked existing controls to force reader mode. Those mechanisms duplicate state already owned by `PublicationsReaderPage` and `DocumentationAssistantPanel`, make the UI dependent on CSS selectors and button text, and would be fragile after #477's reader/governance consolidation.

The associated CSS rules that hid the existing publication tabs, reader controls and assistant launcher were also rejected. The consolidated implementation keeps those controls available and preserves their existing React lifecycle.

The concurrent branch's network/raster performance retuning was not replayed in this first consolidation commit. Its smaller range/DPR numbers may be useful, but the old branch supplied contract checks rather than production-like comparative measurements. Performance policy should be changed only with representative manual benchmarks on the current combined tree.

## Validation requirement

The consolidated branch must be validated on its own exact head. Green checks from PR #481's pre-#477 head are historical evidence only and do not prove the combined post-#477 tree.

At minimum, the Publications Reader and Document Control domain suites must pass. Because #477 added governance and cross-domain migration/security gates, any triggered Document Control Governance and Reliability workflows must also be green before the PR can leave draft.
