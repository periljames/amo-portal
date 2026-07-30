from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Missing expected anchor in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


platform = Path("frontend/src/pages/platform/components/PlatformShared.tsx")
replace_once(
    platform,
    '''  const signInWithPlatformAccount = () => {\n    endSession("manual");\n    navigate("/login", {\n      replace: true,\n      state: { from: location.pathname + location.search },\n    });\n  };''',
    '''  const signInWithPlatformAccount = () => {\n    endSession("manual");\n    navigate("/login", { replace: true });\n  };''',
)

platform_test = Path("frontend/src/services/platformControl.test.ts")
replace_once(
    platform_test,
    '''  it("hydrates the authoritative platform user before denying access", () => {\n    expect(platformSharedSource).toContain("fetchCurrentUser()");\n    expect(platformSharedSource).toContain('accessState === "checking"');\n    expect(platformSharedSource).toContain('endSession("manual")');\n    expect(platformSharedSource).toContain("Sign in with platform account");\n  });''',
    '''  it("hydrates the authoritative platform user before denying access", () => {\n    expect(platformSharedSource).toContain("fetchCurrentUser()");\n    expect(platformSharedSource).toContain('accessState === "checking"');\n    expect(platformSharedSource).toContain('endSession("manual")');\n    expect(platformSharedSource).toContain("Sign in with platform account");\n  });\n\n  it("does not return a tenant login to a denied platform route", () => {\n    const signInHandler = platformSharedSource.match(\n      /const signInWithPlatformAccount = \\(\\) => \\{[\\s\\S]*?\\n  \\};/,\n    )?.[0] ?? "";\n\n    expect(signInHandler).toContain('navigate("/login", { replace: true })');\n    expect(signInHandler).not.toContain("state:");\n    expect(signInHandler).not.toContain("location.pathname");\n  });''',
)

print("Removed the denied platform return target and added regression coverage.")
