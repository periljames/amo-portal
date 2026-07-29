from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Missing expected anchor in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


platform = Path("frontend/src/pages/platform/components/PlatformShared.tsx")
replace_once(
    platform,
    'import { endSession, getCachedUser } from "../../../services/auth";',
    'import { endSession, fetchCurrentUser, getCachedUser, isAuthenticated, type PortalUser } from "../../../services/auth";',
)
replace_once(
    platform,
    '''}> = ({ title, subtitle, actions, children }) => {\n  const user = getCachedUser();\n  const navigate = useNavigate();\n  const location = useLocation();\n  const searchRef = useRef<HTMLInputElement | null>(null);''',
    '''}> = ({ title, subtitle, actions, children }) => {\n  const navigate = useNavigate();\n  const location = useLocation();\n  const searchRef = useRef<HTMLInputElement | null>(null);''',
)
replace_once(
    platform,
    '''  const [bootstrapSnapshot, setBootstrapSnapshot] = useState<PlatformConsoleSnapshot | null>(null);\n  const [query, setQuery] = useState("");\n  const [searching, setSearching] = useState(false);\n  const [results, setResults] = useState<PlatformConsoleSearchResult[]>([]);\n  const realtime = usePlatformRealtime(Boolean(user?.is_superuser));\n  const snapshot = realtime.snapshot ?? bootstrapSnapshot;\n  const resolvedTheme = theme === "system" ? systemTheme : theme;\n\n  useEffect(() => {\n    if (!user?.is_superuser) return;\n    void platformConsoleApi.bootstrap().then(setBootstrapSnapshot).catch(() => undefined);\n  }, [user?.is_superuser]);''',
    '''  const [bootstrapSnapshot, setBootstrapSnapshot] = useState<PlatformConsoleSnapshot | null>(null);\n  const [query, setQuery] = useState("");\n  const [searching, setSearching] = useState(false);\n  const [results, setResults] = useState<PlatformConsoleSearchResult[]>([]);\n  const [user, setUser] = useState<PortalUser | null>(() => getCachedUser());\n  const [accessState, setAccessState] = useState<"checking" | "allowed" | "denied">(\n    () => (isAuthenticated() ? "checking" : "denied"),\n  );\n  const [accessError, setAccessError] = useState<string | null>(null);\n  const [accessAttempt, setAccessAttempt] = useState(0);\n  const realtime = usePlatformRealtime(accessState === "allowed");\n  const snapshot = realtime.snapshot ?? bootstrapSnapshot;\n  const resolvedTheme = theme === "system" ? systemTheme : theme;\n  const style = {\n    "--platform-accent": accent,\n    "--platform-accent-rgb": accentRgb(accent),\n  } as React.CSSProperties;\n\n  useEffect(() => {\n    let active = true;\n    if (!isAuthenticated()) {\n      setUser(null);\n      setAccessError(null);\n      setAccessState("denied");\n      return () => { active = false; };\n    }\n\n    setAccessError(null);\n    setAccessState("checking");\n    void fetchCurrentUser()\n      .then((freshUser) => {\n        if (!active) return;\n        setUser(freshUser);\n        setAccessState(freshUser.is_superuser ? "allowed" : "denied");\n      })\n      .catch((error: unknown) => {\n        if (!active) return;\n        setUser(getCachedUser());\n        setAccessError(error instanceof Error ? error.message : "Unable to verify platform access.");\n        setAccessState("denied");\n      });\n\n    return () => { active = false; };\n  }, [accessAttempt]);\n\n  useEffect(() => {\n    if (accessState !== "allowed") return;\n    void platformConsoleApi.bootstrap().then(setBootstrapSnapshot).catch(() => undefined);\n  }, [accessState]);''',
)
replace_once(
    platform,
    '''  if (!user?.is_superuser) {\n    return (\n      <main className="platform-access-denied">\n        <section className="platform-card">\n          <h1>Platform access required</h1>\n          <p>This console is available only to global platform superusers.</p>\n          <button className="platform-btn primary" onClick={() => navigate("/login", { replace: true })}>Go to login</button>\n        </section>\n      </main>\n    );\n  }\n\n  const style = {\n    "--platform-accent": accent,\n    "--platform-accent-rgb": accentRgb(accent),\n  } as React.CSSProperties;''',
    '''  const signInWithPlatformAccount = () => {\n    endSession("manual");\n    navigate("/login", {\n      replace: true,\n      state: { from: location.pathname + location.search },\n    });\n  };\n\n  if (accessState === "checking") {\n    return (\n      <div className="platform-shell" data-platform-theme={resolvedTheme} style={style}>\n        <main className="platform-access-denied">\n          <section className="platform-card" role="status" aria-live="polite">\n            <h1>Verifying platform access</h1>\n            <p>Confirming this session with the platform control plane…</p>\n          </section>\n        </main>\n      </div>\n    );\n  }\n\n  if (accessState !== "allowed" || !user?.is_superuser) {\n    return (\n      <div className="platform-shell" data-platform-theme={resolvedTheme} style={style}>\n        <main className="platform-access-denied">\n          <section className="platform-card">\n            <h1>Platform access required</h1>\n            <p>{accessError ? `Platform access could not be verified: ${accessError}` : "This console is available only to global platform superusers."}</p>\n            {accessError && isAuthenticated() ? (\n              <button className="platform-btn" onClick={() => setAccessAttempt((attempt) => attempt + 1)}>Retry access check</button>\n            ) : null}\n            <button className="platform-btn primary" onClick={signInWithPlatformAccount}>Sign in with platform account</button>\n          </section>\n        </main>\n      </div>\n    );\n  }''',
)

warning_file = Path("backend/amodb/apps/doc_control/knowledge_workspace_router.py")
replace_once(
    warning_file,
    "from pydantic import BaseModel, Field",
    "from pydantic import BaseModel, ConfigDict, Field",
)
replace_once(
    warning_file,
    '''class ExecutionProfileUpdate(BaseModel):\n    execution_type:''',
    '''class ExecutionProfileUpdate(BaseModel):\n    model_config = ConfigDict(populate_by_name=True)\n\n    execution_type:''',
)
replace_once(
    warning_file,
    '    schema: dict[str, Any] = Field(default_factory=dict)',
    '    execution_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")',
)
replace_once(
    warning_file,
    "    row.schema_json = payload.schema",
    "    row.schema_json = payload.execution_schema",
)

platform_test = Path("frontend/src/services/platformControl.test.ts")
replace_once(
    platform_test,
    'import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";',
    'import { readFileSync } from "node:fs";\nimport { fileURLToPath } from "node:url";\n\nimport { afterEach, beforeEach, describe, expect, it, vi } from "vitest";',
)
replace_once(
    platform_test,
    'describe("platform SaaS control API", () => {',
    '''const platformSharedSource = readFileSync(\n  fileURLToPath(new URL("../pages/platform/components/PlatformShared.tsx", import.meta.url)),\n  "utf8",\n);\n\ndescribe("platform SaaS control API", () => {''',
)
replace_once(
    platform_test,
    '''  it("keeps direct platform page navigation in the SPA", () => {''',
    '''  it("hydrates the authoritative platform user before denying access", () => {\n    expect(platformSharedSource).toContain("fetchCurrentUser()");\n    expect(platformSharedSource).toContain('accessState === "checking"');\n    expect(platformSharedSource).toContain('endSession("manual")');\n    expect(platformSharedSource).toContain("Sign in with platform account");\n  });\n\n  it("keeps direct platform page navigation in the SPA", () => {''',
)

backend_test = Path("backend/amodb/apps/doc_control/tests/test_knowledge_workspace_schema_contract.py")
backend_test.parent.mkdir(parents=True, exist_ok=True)
backend_test.write_text(
    '''from amodb.apps.doc_control.knowledge_workspace_router import ExecutionProfileUpdate\n\n\ndef test_execution_profile_preserves_external_schema_alias_without_shadowing_base_model():\n    payload = ExecutionProfileUpdate.model_validate({\n        "execution_type": "PORTAL_FORM",\n        "submission_mode": "PORTAL_SUBMISSION",\n        "schema": {"type": "object", "properties": {"finding": {"type": "string"}}},\n    })\n\n    assert payload.execution_schema["type"] == "object"\n    assert payload.model_dump(by_alias=True)["schema"] == payload.execution_schema\n    assert "schema" not in ExecutionProfileUpdate.model_fields\n''',
    encoding="utf-8",
)

print("Applied platform session hydration, login-loop, and execution-profile schema fixes.")
