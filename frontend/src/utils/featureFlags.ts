export const isUiShellV2Enabled = (): boolean => {
  const flag = import.meta.env.VITE_UI_SHELL_V2;
  if (flag !== undefined) {
    return flag !== "0" && flag !== "false";
  }
  return import.meta.env.DEV;
};


export const isCursorLayerEnabled = (): boolean => {
  const flag = import.meta.env.VITE_UI_CURSOR_LAYER;
  if (flag !== undefined) return flag !== "0" && flag !== "false";
  return false;
};
