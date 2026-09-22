# Quality and Document Control layout

`frontend/src/styles/components/governed-workspace-layout.css` owns the shared
fill chain. `DepartmentLayoutImpl` identifies the module with
`data-workspace-module`; this does not depend on a route-specific HTML class.

The tenant workspace owns the dynamic viewport. Its main element owns page
scrolling. Context navigation and status banners retain their natural height.
Content and module shells grow into the remaining space, and grow beyond it
when required. Do not calculate another viewport height in a page shell.

Feature styles own their internal composition and appearance. Dialogs, virtual
grids and document canvases may have their own bounded scroll regions. Do not
apply overflow hidden to ordinary form or register page bodies.

The PDF integration measures its actual top against the visual viewport and
updates on resize and captured ancestor scrolling. There is no fixed minimum
height that can push the reader outside a short viewport. The active path is
`PdfReaderCore` → `PdfReaderCoreV5` (navigation) → `PdfReaderCoreV4` (virtualized
renderer). V2/V3 compatibility exports and unused V1/V2 CSS have been removed.

Geometry regression coverage: `tests/e2e/governed-workspace-layout.spec.ts`.
Reader architecture coverage: `src/pages/manuals/PdfReaderArchitecture.contract.test.ts`.
These checks do not replace authenticated workflow and large-document release tests.

The geometry suite covers six shell compositions at desktop, tablet, phone and
short landscape sizes, including long-content reachability. These are isolated
production-CSS fixtures, not authenticated page screenshots.

The bounded-register integration suite reached expired-session login on
revalidation. The live PDF suite requires authenticated publication fixture
configuration and was skipped. Complete those release checks before sign-off;
this cleanup does not claim a new real-document rendering-time measurement.
