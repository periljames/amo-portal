from __future__ import annotations

import re
from pathlib import Path

# script expected location: backend/amodb/scripts/fix_users_fk_types.py
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent  # backend/amodb

# Support both layouts:
# 1) backend/amodb/apps
# 2) backend/amodb/amodb/apps
if (ROOT / "apps").exists():
    APPS_DIR = ROOT / "apps"
elif (ROOT / "amodb" / "apps").exists():
    APPS_DIR = ROOT / "amodb" / "apps"
else:
    raise SystemExit(f"Could not find apps directory at: {ROOT / 'apps'} or {ROOT / 'amodb' / 'apps'}")

# Matches: Column(Integer, ForeignKey("users.id"... (any whitespace/newlines)
FK_INT_PATTERN = re.compile(
    r"Column\(\s*Integer\s*,\s*ForeignKey\(\s*['\"]users\.id['\"]",
    flags=re.MULTILINE,
)

# Try to ensure String is imported if the file uses the parenthesized import block style
SQLA_IMPORT_BLOCK = re.compile(
    r"from\s+sqlalchemy\s+import\s+\(\s*.*?\)\s*",
    flags=re.DOTALL,
)

def ensure_string_import(text: str) -> str:
    m = SQLA_IMPORT_BLOCK.search(text)
    if not m:
        return text  # other import styles often already include String

    block = m.group(0)
    if re.search(r"\bString\b", block):
        return text

    if re.search(r"\bInteger\s*,", block):
        new_block = re.sub(r"\bInteger\s*,", "Integer,\n    String,", block, count=1)
    else:
        new_block = re.sub(r"\)\s*$", "    String,\n)\n", block)

    return text[: m.start()] + new_block + text[m.end() :]

def patch_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")

    if not FK_INT_PATTERN.search(original):
        return False

    patched = FK_INT_PATTERN.sub(
        lambda mm: mm.group(0).replace("Integer", "String(36)", 1),
        original,
    )

    patched = ensure_string_import(patched)

    if patched != original:
        path.write_text(patched, encoding="utf-8")
        return True
    return False

def main() -> None:
    changed = 0
    for file in APPS_DIR.rglob("models.py"):
        if patch_file(file):
            changed += 1
            print(f"Patched: {file}")

    print(f"\nDone. Files changed: {changed}")

if __name__ == "__main__":
    main()
