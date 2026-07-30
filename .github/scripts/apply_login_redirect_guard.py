from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Missing expected anchor in {path}: {old[:160]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


login_page = Path("frontend/src/pages/LoginPage.tsx")
replace_once(
    login_page,
    'import { preloadWorkspaceForUser } from "../services/routePreloader";',
    'import { preloadWorkspaceForUser } from "../services/routePreloader";\nimport { resolvePostLoginReturnTarget } from "../app/loginRedirect";',
)

replace_once(
    login_page,
    '''      const u = getCachedUser();
      if (isPlatformUser(u)) {
        navigate("/platform/control", { replace: true });
        return;
      }
      const admin = isAdminUser(u);
      const requiresOnboarding = !!u?.must_change_password;
      if (requiresOnboarding && !redirectedRef.current) {
        redirectedRef.current = true;
        navigate(`/maintenance/${slug}/onboarding/setup`, { replace: true });
        return;
      }
      if (fromState) {
        navigate(fromState, { replace: true });
        return;
      }

      const landingDept = admin ? "admin" : (ctx.department || null);''',
    '''      const u = getCachedUser();
      const platformUser = isPlatformUser(u);
      const admin = isAdminUser(u);
      const requiresOnboarding = !!u?.must_change_password;
      if (requiresOnboarding && !redirectedRef.current) {
        redirectedRef.current = true;
        navigate(`/maintenance/${slug}/onboarding/setup`, { replace: true });
        return;
      }

      const returnTarget = resolvePostLoginReturnTarget(fromState, platformUser);
      if (returnTarget) {
        navigate(returnTarget, { replace: true });
        return;
      }
      if (platformUser) {
        navigate("/platform/control", { replace: true });
        return;
      }

      const landingDept = admin ? "admin" : (ctx.department || null);''',
)

replace_once(
    login_page,
    '''      if (fromState) {
        navigate(fromState, { replace: true });
        return;
      }

      const ctx = getContext();
      const signedInUser = getCachedUser();
      if (isPlatformUser(signedInUser)) {
        navigate("/platform/control", { replace: true });
        return;
      }
      const admin = isAdminUser(signedInUser);''',
    '''      const ctx = getContext();
      const signedInUser = auth.user || getCachedUser();
      const platformUser = isPlatformUser(signedInUser);
      const returnTarget = resolvePostLoginReturnTarget(fromState, platformUser);
      if (returnTarget) {
        navigate(returnTarget, { replace: true });
        return;
      }
      if (platformUser) {
        navigate("/platform/control", { replace: true });
        return;
      }
      const admin = isAdminUser(signedInUser);''',
)

print("Applied account-aware post-login return target validation.")
