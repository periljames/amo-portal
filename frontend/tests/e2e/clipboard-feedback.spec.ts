import { expect, test, type Page, type Route } from "@playwright/test";

type ClipboardHarness = {
  fail: boolean;
  calls: number;
  values: string[];
};

type HarnessWindow = Window & {
  __clipboardFeedbackHarness?: ClipboardHarness;
};

async function prepareClipboardHarness(page: Page, reducedMotion = false) {
  if (reducedMotion) {
    await page.emulateMedia({ reducedMotion: "reduce" });
  }

  await page.addInitScript(() => {
    const harness: ClipboardHarness = { fail: false, calls: 0, values: [] };
    (window as HarnessWindow).__clipboardFeedbackHarness = harness;
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (value: string) => {
          harness.calls += 1;
          harness.values.push(value);
          if (harness.fail) {
            throw new DOMException("Clipboard permission denied", "NotAllowedError");
          }
        },
      },
    });
  });

  await page.route("**/*", async (route: Route) => {
    const resourceType = route.request().resourceType();
    if (resourceType === "fetch" || resourceType === "xhr") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "{}",
      });
      return;
    }
    await route.continue();
  });

  await page.goto("/");
  await page.evaluate(() => {
    const button = document.createElement("button");
    button.id = "clipboard-feedback-test-trigger";
    button.type = "button";
    button.textContent = "Copy test value";
    button.addEventListener("click", () => {
      void navigator.clipboard.writeText("calendar-subscription-link").catch(() => undefined);
    });
    document.body.appendChild(button);
  });
}

test("announces success, handles repeated copies and cleans up", async ({ page }) => {
  await prepareClipboardHarness(page);

  const trigger = page.getByRole("button", { name: "Copy test value" });
  const toast = page.locator("#amo-clipboard-feedback");

  await trigger.click();

  await expect(toast).toBeVisible();
  await expect(toast).toContainText("Content copied successfully");
  await expect(toast).toHaveAttribute("role", "status");
  await expect(toast).toHaveAttribute("aria-live", "polite");
  await expect(toast).toHaveAttribute("aria-atomic", "true");
  await expect(trigger).toHaveAttribute("data-copy-feedback", "success");

  await trigger.click();

  await expect.poll(() => page.evaluate(() => (
    (window as HarnessWindow).__clipboardFeedbackHarness?.calls ?? 0
  ))).toBe(2);
  await expect(page.locator("#amo-clipboard-feedback")).toHaveCount(1);
  await expect(toast).toContainText("Content copied successfully");
  await expect(trigger).toHaveAttribute("data-copy-feedback", "success");

  await expect(trigger).not.toHaveAttribute("data-copy-feedback", /.+/, { timeout: 3_500 });
  await expect(toast).toBeHidden({ timeout: 3_500 });
});

test("shows failure without swallowing the clipboard rejection", async ({ page }) => {
  await prepareClipboardHarness(page);
  await page.evaluate(() => {
    const harness = (window as HarnessWindow).__clipboardFeedbackHarness;
    if (harness) harness.fail = true;
  });

  const trigger = page.getByRole("button", { name: "Copy test value" });
  const toast = page.locator("#amo-clipboard-feedback");

  await trigger.click();

  await expect(toast).toBeVisible();
  await expect(toast).toContainText("Copy failed. Please try again.");
  await expect(toast).toHaveAttribute("data-state", "error");
  await expect(trigger).toHaveAttribute("data-copy-feedback", "error");
  await expect.poll(() => page.evaluate(() => (
    (window as HarnessWindow).__clipboardFeedbackHarness?.calls ?? 0
  ))).toBe(1);
});

test("disables clipboard animations when reduced motion is requested", async ({ page }) => {
  await prepareClipboardHarness(page, true);

  const trigger = page.getByRole("button", { name: "Copy test value" });
  const toast = page.locator("#amo-clipboard-feedback");
  await trigger.click();
  await expect(toast).toBeVisible();

  const styles = await page.evaluate(() => {
    const toastElement = document.getElementById("amo-clipboard-feedback");
    const triggerElement = document.getElementById("clipboard-feedback-test-trigger");
    if (!toastElement || !triggerElement) throw new Error("Clipboard feedback elements are missing");
    return {
      toastAnimation: getComputedStyle(toastElement).animationName,
      toastTransition: getComputedStyle(toastElement).transitionDuration,
      triggerAnimation: getComputedStyle(triggerElement).animationName,
      triggerTransition: getComputedStyle(triggerElement).transitionDuration,
    };
  });

  expect(styles.toastAnimation).toBe("none");
  expect(styles.toastTransition).toBe("0s");
  expect(styles.triggerAnimation).toBe("none");
  expect(styles.triggerTransition).toBe("0s");
});
