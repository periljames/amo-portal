import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { expect, test } from "@playwright/test";

// Exercise production styles without authentication or API availability.
function stylesheet(path: string): string {
  return readFileSync(path, "utf8").replace(/@import\s+"([^"]+)";/g, (_, child: string) =>
    stylesheet(resolve(dirname(path), child)));
}
const styles = stylesheet(resolve("src/styles/index.css")) +
  stylesheet(resolve("src/pages/qualityAudits/quality-audits-workspace.css")) +
  stylesheet(resolve("src/pages/documentControl/documentControlWorkspace.css")) +
  stylesheet(resolve("src/styles/qms/register.css")) +
  stylesheet(resolve("src/styles/qms-audit-occurrence-shell.css"));

const surfaces = [
  { module: "quality", body: '<div class="qms-shell"><header>Quality header</header><div class="qms-content"><div class="page">Empty register</div></div></div>' },
  { module: "quality", body: '<div class="qms-audit-occurrence-mount"><div class="qms-audit-occurrence-shell"><header>Stage navigation</header><div class="qms-audit-occurrence-shell__body">Setup</div></div></div>' },
  { module: "document-control", body: '<div class="dc-workspace"><header>Documents</header><main class="dc-workspace__content">Library</main></div>' },
  { module: "quality", body: '<div class="qms-shell"><header>Assurance</header><div class="qms-content"><div class="audit-shell-content"><div class="qa-workspace-shell"><aside class="qa-workspace-rail">Assurance navigation</aside><section class="qa-workspace-main"><div class="page">Overview</div></section></div></div></div></div>' },
  { module: "quality", body: '<main class="qms-register-page"><header>Risk register</header><section class="qms-register-workspace"><div class="qms-register-toolbar">Filters</div><div class="qms-register-empty">No records</div><footer>Pagination</footer></section></main>' },
  { module: "manuals", body: '<div class="manuals-page-shell"><header>Manuals</header><section>Publications</section></div>' },
];

for (const viewport of [{ width: 1920, height: 1080 }, { width: 1024, height: 768 }, { width: 390, height: 844 }, { width: 844, height: 390 }]) {
  for (const [index, surface] of surfaces.entries()) {
    test(`${surface.module} shell ${index} fills ${viewport.width}x${viewport.height} and scrolls long content`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.setContent(`<style>${styles}</style><div class="tenant-shell" data-workspace-module="${surface.module}"><div class="tenant-shell__workspace"><header class="tenant-shell__topbar">Portal</header><main class="tenant-shell__main"><div class="quality-context-bar-host">Context navigation</div><div class="tenant-shell__content">${surface.body}</div></main></div></div>`);
      const geometry = await page.locator(".tenant-shell__content").evaluate((content) => {
        const shell = content.firstElementChild!;
        const bounds = content.getBoundingClientRect();
        return {
          bottom: shell.getBoundingClientRect().bottom + parseFloat(getComputedStyle(content).paddingBottom),
          contentBottom: bounds.bottom,
          documentWidth: document.documentElement.scrollWidth,
          viewportWidth: innerWidth,
          viewportHeight: innerHeight,
        };
      });
      expect(Math.abs(geometry.bottom - geometry.viewportHeight)).toBeLessThanOrEqual(2);
      expect(Math.abs(geometry.contentBottom - geometry.viewportHeight)).toBeLessThanOrEqual(2);
      expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewportWidth);
      await page.locator(".tenant-shell__content > *").evaluate((shell) => {
        const longContent = document.createElement("div");
        longContent.style.height = "1800px";
        longContent.style.flexShrink = "0";
        longContent.textContent = "Long content";
        shell.append(longContent);
      });
      const scroll = await page.locator(".tenant-shell__main").evaluate((main) => {
        main.scrollTop = main.scrollHeight;
        return { top: main.scrollTop, height: main.clientHeight, total: main.scrollHeight };
      });
      expect(scroll.top).toBeGreaterThan(0);
      expect(Math.abs(scroll.top + scroll.height - scroll.total)).toBeLessThanOrEqual(2);
    });
  }
}
