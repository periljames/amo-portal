// src/app/tenantLoader.ts
import { getContext } from "../services/auth";

export function getActiveAmoCode(routeAmoCode?: string | null): string | null {
  return routeAmoCode || getContext().amoSlug || getContext().amoCode || null;
}
