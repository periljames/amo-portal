import test from "node:test";
import assert from "node:assert/strict";
import { LOADER_ESCALATION, pickLoaderPresentation, shouldClearTaskOnRouteChange } from "../../src/components/loading/escalationRules.js";
import { isLoaderGalleryEnabled } from "../../src/components/loading/galleryAccess.js";
import { resolveLoaderContrast } from "../../src/components/loading/contrastMode.js";
import { getPasskeyEnvironmentMessage, getSignerPrimaryAction } from "../../src/pages/esign/passkeyState.js";

const task = {
  allow_overlay: true,
  mode_preference: "auto",
  affects_route: false,
  persistent: false,
};

test("pickLoaderPresentation escalates from inline to section to overlay", () => {
  assert.equal(pickLoaderPresentation(task, 50).mode, "inline");
  assert.equal(pickLoaderPresentation(task, LOADER_ESCALATION.sectionMs + 10).mode, "section");
  const late = pickLoaderPresentation(task, LOADER_ESCALATION.overlayMs + 10);
  assert.equal(late.mode, "overlay");
  assert.equal(late.showOverlay, true);
});

test("pickLoaderPresentation sets long wait hint after threshold", () => {
  const outcome = pickLoaderPresentation(task, LOADER_ESCALATION.longWaitMs + 1);
  assert.equal(outcome.showLongWaitHint, true);
});

test("route change cleanup clears non-persistent tasks", () => {
  assert.equal(shouldClearTaskOnRouteChange({ persistent: false }), true);
  assert.equal(shouldClearTaskOnRouteChange({ persistent: true }), false);
});

test("loader gallery access is admin guarded and production-flagged", () => {
  assert.equal(isLoaderGalleryEnabled({ isAdmin: false, isProd: false, flag: undefined }), false);
  assert.equal(isLoaderGalleryEnabled({ isAdmin: true, isProd: false, flag: undefined }), true);
  assert.equal(isLoaderGalleryEnabled({ isAdmin: true, isProd: true, flag: "0" }), false);
  assert.equal(isLoaderGalleryEnabled({ isAdmin: true, isProd: true, flag: "1" }), true);
});

test("loader contrast mode resolves high when requested", () => {
  assert.equal(resolveLoaderContrast({ requested: "high" }), "high");
  assert.equal(resolveLoaderContrast({ requested: "normal" }), "normal");
});

test("loader contrast auto-elevates for prefers-contrast/forced-colors", () => {
  assert.equal(resolveLoaderContrast({ requested: "normal", prefersContrastMore: true }), "high");
  assert.equal(resolveLoaderContrast({ requested: "normal", forcedColors: true }), "high");
  assert.equal(resolveLoaderContrast({ requested: "normal", rootHighContrastClass: true }), "high");
});


test("passkey signer action label reflects credential availability", () => {
  assert.equal(getSignerPrimaryAction(true), "Sign with passkey");
  assert.equal(getSignerPrimaryAction(false), "Set up passkey to sign");
});

test("passkey environment messages are explicit", () => {
  assert.equal(getPasskeyEnvironmentMessage({ supported: false, secure: true }).includes("not supported"), true);
  assert.equal(getPasskeyEnvironmentMessage({ supported: true, secure: false }).includes("secure connection"), true);
  assert.equal(getPasskeyEnvironmentMessage({ supported: true, secure: true }), "");
});
