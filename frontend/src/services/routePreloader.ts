import { getContext, type LoginContextResponse, type PortalUser } from "./auth";
import { getFirstAccessibleModuleRoute } from "../utils/roleAccess";
import { preloadRoute, scheduleWorkspaceRoutePreload } from "../app/routePreload";
import { readLoginHomeHint } from "./loginHomeHint";
let cancelScheduled: (() => void) | null = null;

/** Before authentication, only warm a previously chosen home; never fan out across modules. */
export function preloadAfterLoginContext(context: LoginContextResponse | null): void {
 if (!context || typeof window === "undefined") return;
 const slug = context.login_slug || context.amo_code;
 if (!slug) return;
 const target = context.is_platform ? "/platform/control" : readLoginHomeHint(slug);
 if (target) void preloadRoute(target).catch(() => undefined);
}

export function preloadWorkspaceForUser(user: PortalUser | null, amoCodeOrSlug?: string | null): void {
 if (!user || typeof window === "undefined") return;
 const ctx = getContext(), amo = amoCodeOrSlug || ctx.amoSlug || ctx.amoCode;
 if (!amo) return;
 cancelScheduled?.();
 cancelScheduled = scheduleWorkspaceRoutePreload([getFirstAccessibleModuleRoute(amo, user, ctx.department)], { firstDelayMs: 1500 });
}
