from pathlib import Path

root = Path(__file__).resolve().parents[2]
component = root / "frontend/src/pages/manuals/DocumentationAssistantPanel.tsx"
text = component.read_text(encoding="utf-8")
old = '''    const stored = Number(window.localStorage.getItem(FLOATING_WIDTH_STORAGE_KEY));
    return Number.isFinite(stored)
      ? clampAssistantWidth(stored, window.innerWidth)
      : clampAssistantWidth(FLOATING_DEFAULT_WIDTH, window.innerWidth);'''
new = '''    const storedValue = window.localStorage.getItem(FLOATING_WIDTH_STORAGE_KEY);
    if (!storedValue) return clampAssistantWidth(FLOATING_DEFAULT_WIDTH, window.innerWidth);
    const stored = Number(storedValue);
    return Number.isFinite(stored)
      ? clampAssistantWidth(stored, window.innerWidth)
      : clampAssistantWidth(FLOATING_DEFAULT_WIDTH, window.innerWidth);'''
if old not in text:
    raise RuntimeError("assistant stored-width anchor missing")
component.write_text(text.replace(old, new, 1), encoding="utf-8")

test_file = root / "frontend/src/pages/rostering/documentationAssistantUx.test.ts"
test_text = test_file.read_text(encoding="utf-8")
old_test = '    expect(assistant).toContain("amo_documentation_assistant_width");\n'
new_test = old_test + '    expect(assistant).toContain("if (!storedValue) return clampAssistantWidth(FLOATING_DEFAULT_WIDTH");\n'
if old_test not in test_text:
    raise RuntimeError("assistant default-width test anchor missing")
test_file.write_text(test_text.replace(old_test, new_test, 1), encoding="utf-8")

print("Assistant default width corrected")
