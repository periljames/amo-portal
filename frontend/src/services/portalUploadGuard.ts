import { reportUploadError, revealPortalErrorTarget } from "./portalError";

function fileExtension(file: File): string {
  const index = file.name.lastIndexOf(".");
  return index >= 0 ? file.name.slice(index).toLowerCase() : "";
}

function matchesAccept(file: File, accept: string): boolean {
  const rules = accept.split(",").map((rule) => rule.trim().toLowerCase()).filter(Boolean);
  if (!rules.length) return true;
  const mime = file.type.toLowerCase();
  const extension = fileExtension(file);
  return rules.some((rule) => {
    if (rule.startsWith(".")) return extension === rule;
    if (rule.endsWith("/*")) return mime.startsWith(rule.slice(0, -1));
    return mime === rule;
  });
}

function parseSize(value: string | undefined): number {
  if (!value) return 0;
  const normalized = value.trim().toLowerCase();
  const number = Number.parseFloat(normalized);
  if (!Number.isFinite(number) || number <= 0) return 0;
  if (normalized.endsWith("gib") || normalized.endsWith("gb")) return Math.round(number * 1024 * 1024 * 1024);
  if (normalized.endsWith("mib") || normalized.endsWith("mb")) return Math.round(number * 1024 * 1024);
  if (normalized.endsWith("kib") || normalized.endsWith("kb")) return Math.round(number * 1024);
  return Math.round(number);
}

function maximumBytes(input: HTMLInputElement): number {
  const dataset = input.dataset;
  return parseSize(
    dataset.maxSizeBytes
      || dataset.maxFileSize
      || dataset.maxUploadSize
      || (dataset.maxSizeMb ? `${dataset.maxSizeMb}MB` : undefined),
  );
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024) return `${Math.round(bytes / (1024 * 1024 * 1024) * 10) / 10} GiB`;
  if (bytes >= 1024 * 1024) return `${Math.round(bytes / (1024 * 1024) * 10) / 10} MiB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KiB`;
  return `${bytes} bytes`;
}

function validateFileInput(input: HTMLInputElement): void {
  input.setCustomValidity("");
  const files = [...(input.files || [])];
  if (!files.length) return;

  const invalidType = files.find((file) => input.accept && !matchesAccept(file, input.accept));
  if (invalidType) {
    const message = `${invalidType.name} is not an accepted file type. Choose one of: ${input.accept}.`;
    input.setCustomValidity(message);
    reportUploadError(message, {
      target: input,
      actionLabel: "Choose another file",
      action: () => { revealPortalErrorTarget(input); input.click(); },
      dedupeKey: `upload-type:${input.name || input.id}:${invalidType.name}`,
    });
    revealPortalErrorTarget(input);
    return;
  }

  const maximum = maximumBytes(input);
  if (!maximum) return;
  const oversized = files.find((file) => file.size > maximum);
  if (!oversized) return;

  const message = `${oversized.name} is ${formatBytes(oversized.size)}, which exceeds the ${formatBytes(maximum)} upload limit.`;
  input.setCustomValidity(message);
  reportUploadError(message, {
    target: input,
    actionLabel: "Choose a smaller file",
    action: () => { revealPortalErrorTarget(input); input.click(); },
    dedupeKey: `upload-size:${input.name || input.id}:${oversized.name}:${maximum}`,
  });
  revealPortalErrorTarget(input);
}

export function installPortalUploadGuard(): () => void {
  if (typeof document === "undefined") return () => undefined;
  const onChange = (event: Event) => {
    const target = event.target;
    if (target instanceof HTMLInputElement && target.type === "file") validateFileInput(target);
  };
  document.addEventListener("change", onChange, true);
  return () => document.removeEventListener("change", onChange, true);
}
