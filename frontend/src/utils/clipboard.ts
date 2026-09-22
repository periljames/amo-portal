/** Copy text with Clipboard API, falling back to a temporary textarea for non-secure contexts. */
export async function copyTextToClipboard(value: string): Promise<boolean> {
  const text = String(value || "");
  if (!text) return false;
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to execCommand path.
  }
  try {
    const doc = typeof globalThis !== "undefined" ? globalThis.document : undefined;
    if (!doc?.body?.appendChild || !doc.createElement) return false;
    const area = doc.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    area.style.top = "0";
    doc.body.appendChild(area);
    area.select();
    area.setSelectionRange(0, text.length);
    const ok = typeof doc.execCommand === "function" ? doc.execCommand("copy") : false;
    doc.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
}
