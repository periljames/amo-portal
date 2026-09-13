/** One opening primitive for the toolbar and Ctrl/Cmd+K. */
export const QMS_COMMAND_PALETTE_OPEN = "qms:command-palette:open";
export function openQmsCommandPalette(): void {
  window.dispatchEvent(new Event(QMS_COMMAND_PALETTE_OPEN));
}
