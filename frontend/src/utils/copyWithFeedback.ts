export type CopyFeedbackState = "idle" | "success" | "error";

export async function copyWithFeedback(
  value: string,
  onStateChange: (state: CopyFeedbackState) => void,
): Promise<void> {
  if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
    onStateChange("error");
    throw new Error("Clipboard access is not available in this browser.");
  }

  try {
    await navigator.clipboard.writeText(value);
    onStateChange("success");
  } catch (error) {
    onStateChange("error");
    throw error;
  }
}
