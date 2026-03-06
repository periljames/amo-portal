export declare function buildPasskeyLabel(item: { nickname?: string | null; created_at: string }): string;
export declare function validatePasskeyNickname(value: string | null | undefined): { ok: boolean; normalized?: string | null; error?: string };
