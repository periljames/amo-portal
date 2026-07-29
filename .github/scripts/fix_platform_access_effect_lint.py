from pathlib import Path

path = Path("frontend/src/pages/platform/components/PlatformShared.tsx")
text = path.read_text(encoding="utf-8")
old = '''  useEffect(() => {\n    let active = true;\n    if (!isAuthenticated()) {\n      setUser(null);\n      setAccessError(null);\n      setAccessState("denied");\n      return () => { active = false; };\n    }\n\n    setAccessError(null);\n    setAccessState("checking");\n    void fetchCurrentUser()'''
new = '''  useEffect(() => {\n    let active = true;\n    if (!isAuthenticated()) return () => { active = false; };\n\n    void fetchCurrentUser()'''
if old not in text:
    raise RuntimeError("Platform access effect anchor was not found")
text = text.replace(old, new, 1)
old_retry = '''              <button className="platform-btn" onClick={() => setAccessAttempt((attempt) => attempt + 1)}>Retry access check</button>'''
new_retry = '''              <button\n                className="platform-btn"\n                onClick={() => {\n                  setAccessError(null);\n                  setAccessState("checking");\n                  setAccessAttempt((attempt) => attempt + 1);\n                }}\n              >\n                Retry access check\n              </button>'''
if old_retry not in text:
    raise RuntimeError("Platform access retry anchor was not found")
path.write_text(text.replace(old_retry, new_retry, 1), encoding="utf-8")
print("Moved platform access state resets out of the effect body.")
