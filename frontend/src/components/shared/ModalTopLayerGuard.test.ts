import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const guard = readFileSync(new URL("./ModalTopLayerGuard.tsx", import.meta.url), "utf8");
const guardCss = readFileSync(new URL("../../styles/modal-top-layer.css", import.meta.url), "utf8");
const main = readFileSync(new URL("../../main.tsx", import.meta.url), "utf8");
const routeGate = readFileSync(new URL("../QMS/QualityEnhancementsRouteGate.tsx", import.meta.url), "utf8");
const standaloneManuals = readFileSync(new URL("../../standalone/manuals-main.tsx", import.meta.url), "utf8");
const workforce = readFileSync(
  new URL("../../pages/rostering/components/WorkforceHrWorkspace.tsx", import.meta.url),
  "utf8",
);

describe("portal-wide modal top layer", () => {
  it("promotes every visible ARIA modal instead of relying on route z-index values", () => {
    expect(guard).toContain("'[aria-modal=\"true\"]'");
    expect(guard).toContain("MutationObserver");
    expect(guard).toContain("showPopover");
    expect(guard).toContain(":popover-open");
    expect(guard).toContain("selectTopLayerHost");
    expect(guard).toContain("viewportWidth * 0.88");
    expect(guard).toContain("portal-modal-fallback-ancestor");
  });

  it("keeps full-height fixed edge drawers as layout hosts instead of centring them", () => {
    expect(guard).toContain("coversViewportHeight");
    expect(guard).toContain("touchesViewportEdge");
    expect(guard).toContain('const edgeDrawer = position === "fixed" && coversViewportHeight && touchesViewportEdge');
    expect(guard).toContain("coversViewport || edgeDrawer");
  });

  it("mounts the guard in both portal entry paths", () => {
    expect(main).toContain("<QualityEnhancementsRouteGate />");
    expect(routeGate).toContain("<ModalTopLayerGuard />");
    expect(standaloneManuals).toContain("<ModalTopLayerGuard />");
  });

  it("covers the Workforce contract and decision dialogs that exposed the defect", () => {
    expect(workforce).toContain('className="hr-decision hr-contract-editor"');
    expect(workforce).toContain('aria-modal="true"');
    expect(guard).toContain("MODAL_SELECTOR");
    expect(guardCss).toContain(".portal-modal-top-layer--surface");
    expect(guardCss).toContain("z-index: 2147483000 !important");
    expect(guardCss).not.toContain("backdrop-filter: blur");
  });

  it("locks page scrolling and includes a non-Popover browser fallback", () => {
    expect(guardCss).toContain("body.portal-modal-layer-active");
    expect(guardCss).toContain("overflow: hidden !important");
    expect(guardCss).toContain(".portal-modal-fallback-host");
    expect(guardCss).toContain("transform: none !important");
    expect(guard).toContain("clearAddedPopoverAttribute");
  });
});