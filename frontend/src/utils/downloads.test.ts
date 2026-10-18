import { describe, expect, it, vi, afterEach } from "vitest";
import { resolveDownloadFilename, sanitizeDownloadFilename, saveDownloadedFile } from "./downloads";

const id = "f231f732-d27b-4bbd-8b47-a2816ef931d5";

describe("download filenames", () => {
  it("prefers UTF-8 names including a language tag over the ASCII fallback", () => {
    expect(resolveDownloadFilename("attachment; filename=report.pdf; filename* = UTF-8'en'R%C3%A9sum%C3%A9.pdf", "download"))
      .toBe("Résumé.pdf");
  });
  it("retains a quoted semicolon and tolerates malformed percent encoding", () => {
    expect(resolveDownloadFilename('attachment; filename="Audit; final.pdf"', "download")).toBe("Audit; final.pdf");
    expect(resolveDownloadFilename("attachment; filename*=UTF-8''100%ready.pdf", "download")).toBe("100%ready.pdf");
  });
  it("removes internal UUIDs without losing the extension or business label", () => {
    expect(sanitizeDownloadFilename(`CAR-SAF-26-005-${id}-evidence.zip`)).toBe("CAR-SAF-26-005-evidence.zip");
    expect(sanitizeDownloadFilename(`${id}.pdf`)).toBe("download.pdf");
    expect(sanitizeDownloadFilename(`${id.replaceAll("-", "")}_Audit report.pdf`)).toBe("Audit report.pdf");
    expect(sanitizeDownloadFilename(`${"a".repeat(64)}.json`)).toBe(`${"a".repeat(64)}.json`);
    expect(resolveDownloadFilename(null, `training-${id}`, "application/pdf")).toBe("training.pdf");
  });
  it("keeps long extensions, Unicode and revision identifiers", () => {
    expect(sanitizeDownloadFilename(`${"é".repeat(200)}-rev-02.docx`)).toHaveLength(180);
    expect(sanitizeDownloadFilename(`${"é".repeat(200)}-rev-02.docx`)).toMatch(/\.docx$/);
    expect(sanitizeDownloadFilename("SL-QMS-29 Rev 01.docx")).toBe("SL-QMS-29 Rev 01.docx");
  });
  it("blocks paths, control characters and Windows reserved names", () => {
    expect(sanitizeDownloadFilename("../CAR/26/005\r\n.pdf")).toBe("CAR-26-005.pdf");
    expect(sanitizeDownloadFilename("CON.pdf")).toBe("file-CON.pdf");
  });
});

afterEach(() => vi.unstubAllGlobals());

it("saves a typed blob with an extension and revokes its URL after the click", () => {
  const link = { href: "", download: "", click: vi.fn() };
  const revokeObjectURL = vi.fn();
  const scheduled: Array<() => void> = [];
  vi.stubGlobal("document", { createElement: () => link, body: { appendChild: vi.fn(), removeChild: vi.fn() } });
  vi.stubGlobal("window", { URL: { createObjectURL: () => "blob:test", revokeObjectURL }, setTimeout: (fn: () => void) => scheduled.push(fn) });
  saveDownloadedFile(new Blob(["pdf"], { type: "application/pdf" }), `audit-${id}`);
  expect(link.download).toBe("audit.pdf");
  expect(link.click).toHaveBeenCalledOnce();
  expect(revokeObjectURL).not.toHaveBeenCalled();
  scheduled[0]();
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:test");
});
