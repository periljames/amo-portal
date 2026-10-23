import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import type { QmsMission } from "../../../services/qmsMissions";
import { getCachedUser } from "../../../services/auth";

function prefix(amoCode: string, mission: QmsMission) {
  return `qms-change-draft:${getCachedUser()?.id || "unknown"}:${amoCode.toLowerCase()}:${mission.id}:${mission.updated_at}:`;
}

// Drafts stay in this authenticated tab. A newer server version gets a new key
// so an old draft cannot silently overwrite another person's saved work.
export function useMissionDraft<T>(amoCode: string, mission: QmsMission, field: string, initial: T): [T, Dispatch<SetStateAction<T>>] {
  const key = prefix(amoCode, mission) + field;
  const [value, setValue] = useState<T>(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(key) || "null");
      if (saved?.version === 1 && (initial === null || typeof saved.value === typeof initial)) return saved.value as T;
    } catch { /* Storage can be unavailable; keep the in-memory form usable. */ }
    return initial;
  });
  useEffect(() => {
    try { sessionStorage.setItem(key, JSON.stringify({ version: 1, value })); } catch { /* Keep the in-memory value. */ }
  }, [key, value]);
  return [value, setValue];
}

export function clearMissionDraft(amoCode: string, mission: QmsMission) {
  try {
    const keys = Array.from({ length: sessionStorage.length }, (_, index) => sessionStorage.key(index));
    for (const key of keys) if (key?.startsWith(prefix(amoCode, mission))) sessionStorage.removeItem(key);
  } catch { /* Draft storage is optional. */ }
}
