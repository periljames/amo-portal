import { expect, test } from "@playwright/test";

test("parent updates do not reset evidence drafts or start a React update loop", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/__evidence_capture__", route => route.fulfill({ contentType: "text/html", body: '<div id="root"></div>' }));
  await page.route("**/quality/**", route => route.fulfill({ json: { items: [] } }));
  await page.goto("/__evidence_capture__");
  await page.evaluate(async () => {
    const { default: RefreshRuntime } = await import(/* @vite-ignore */ "/@react-refresh");
    RefreshRuntime.injectIntoGlobalHook(window);
    Object.assign(window, { $RefreshReg$: () => {}, $RefreshSig$: () => (type: unknown) => type, __vite_plugin_react_preamble_installed__: true });
    const fixture = await import(/* @vite-ignore */ "/tests/e2e/fixtures/evidenceCaptureHarness.tsx");
    fixture.mount();
  });
  await expect(page.getByLabel("Capture state")).toHaveText("No draft");
  await page.getByLabel("Attach evidence", { exact: true }).setInputFiles({ name: "evidence.txt", mimeType: "text/plain", buffer: Buffer.from("Objective evidence") });
  await expect(page.getByLabel("Capture state")).toHaveText("Draft selected");
  for (let index = 0; index < 10; index++) await page.getByRole("button", { name: /Parent update/ }).click();
  await expect(page.getByLabel("Capture state")).toHaveText("Draft selected");
  await page.getByRole("button", { name: "Clear selected file" }).click();
  await expect(page.getByLabel("Capture state")).toHaveText("No draft");
  expect(errors).toEqual([]);
});
