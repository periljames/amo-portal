export const isUiShellV2Enabled = (): boolean => {
  const flag = import.meta.env.VITE_UI_SHELL_V2;
  if (flag !== undefined) {
    return flag !== "0" && flag !== "false";
  }
  return import.meta.env.DEV;
};
