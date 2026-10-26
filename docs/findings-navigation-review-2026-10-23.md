# Findings layout and QMS navigation

The reference was the user's open finding detail on the authenticated public portal. The original page repeated the finding reference as two headings, stacked four summary facts in two desktop columns, and put the record/acknowledgement section below several full-width cards. The before image is retained locally as `.artifacts/findings-current-before.png`.

The detail now has one record heading, one Findings return link, and source/linked-CAR actions in the header. Four facts use one desktop row. Statement, objective evidence and any CAR response remain fully readable in the main column; record dates and acknowledgement occupy the adjacent column. Smaller containers, including the review drawer, stack the content. The separate observation explanation card is replaced by a short contextual note when no CAR is linked. Existing evidence, dates, permissions, links and data are retained.

The horizontal menu opens the current module automatically and expands one module at a time. Arrow keys, Home/End, Escape and normal Tab navigation use visible controls; collapsed links are excluded from keyboard selection. Focus is restored without scrolling the page. Route changes reset the open menu. Menu entry and chevrons use short animations, with reduced-motion overrides.

Within QMS, a drawer parent row expands its children instead of unexpectedly navigating away; the tiny separate expansion target is removed. Opening a sibling closes the previous branch. Other portal modules retain their parent navigation behavior. The QMS drawer transition is shorter and respects reduced motion.

Verification separates fixture browser checks from the signed-in live review. No finding, CAR, acknowledgement or audit evidence is created or modified as a UI test. Publication and final validation results are recorded below when complete.

Validation on October 23:

- Full TypeScript/production build and modal/heavy-route checks passed. ESLint reported zero errors and one pre-existing `standingAdmin` dependency warning.
- All 24 sidebar, route registry and route preload unit checks passed.
- All 16 production browser checks passed, including five focused finding/navigation cases and traversal of 43 shared QMS register views using isolated API fixtures.
- Signed-in live desktop review confirmed exactly one reference heading, four facts in one row, and the record section alongside the statement at y=260px on a 1440×900 viewport. The 390px mobile review stacked content with no horizontal overflow. Full finding text and source/evidence controls remained present.
- Live menu frame sampling confirmed opacity advanced from 0 to 1 and the 3px entrance translation settled. Opening Audits collapsed Findings; drawer parent selection kept the URL unchanged and opening Assurance closed Work. A live screenshot caught the chevron wrapping to a second grid row; the final CSS supplies a third column and makes the parent hit area span the row. A browser assertion checks both label alignment and full row width.
- The settled live review recorded no page errors or failed HTTP responses; the planned frontend restart briefly returned gateway 502s before readiness recovered to 200.

Local visual evidence: `.artifacts/findings-live-after-desktop.png`, `.artifacts/findings-live-after-mobile.png`, `.artifacts/findings-live-navigation-menu.png`. Runtime release information and the final drawer check follow below.

Final publication: immutable frontend `release-639283618972275469`, entry `/assets/index-CbSj7PBq.js`, public readiness HTTP 200. The CSS-only correction was rebuilt and the five focused production browser tests passed again, including the new geometry assertions. In the authenticated live drawer, the chevron/label center offset measured 0px and the parent button occupied 326px of its 328px row. The final drawer screenshot was inspected after the reveal settled: `.artifacts/findings-live-navigation-drawer-final.png`. Selecting the Findings Register link reached the live register and closed the dropdown; the review then returned to the original finding. No business records were changed.

Final live drawer frame sampling confirmed the 160ms transition from translateX(-367.2px), through -11.2px, to 0px; it remained at 0px after settling. The browser was left on the original finding with the drawer closed.
