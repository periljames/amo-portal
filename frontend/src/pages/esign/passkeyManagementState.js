export const buildPasskeyLabel = (item) => item.nickname || `Passkey · ${new Date(item.created_at).toLocaleDateString()}`;

export const validatePasskeyNickname = (value) => {
  if (value == null || value.trim() === "") return { ok: true, normalized: null };
  const normalized = value.replace(/[\r\n\t]/g, "").trim();
  if (normalized.length > 50) return { ok: false, error: "Nickname must be 50 characters or fewer." };
  return { ok: true, normalized };
};
