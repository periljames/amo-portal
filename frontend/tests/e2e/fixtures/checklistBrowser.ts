import type { Page } from "@playwright/test";
export async function mountChecklistBrowser(page: Page) {
  await page.evaluate(async () => {
    const { default: RefreshRuntime } = await import(/* @vite-ignore */ "/@react-refresh");
    RefreshRuntime.injectIntoGlobalHook(window);
    Object.assign(window, { $RefreshReg$: () => {}, $RefreshSig$: () => (type: unknown) => type, __vite_plugin_react_preamble_installed__: true });
    const fixture = await import(/* @vite-ignore */ "/tests/e2e/fixtures/checklistTableHarness.tsx");
    fixture.mount();
  });
}
export async function openChecklistBrowser(page: Page) {
  await page.route("**/__checklist_table__", (route) => route.fulfill({ contentType: "text/html", body: '<html><body style="margin:0"><div id="root"></div></body></html>' }));
  await page.goto("/__checklist_table__");
  await mountChecklistBrowser(page);
}
