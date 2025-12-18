#!/usr/bin/env python3
"""
alembic_doctor.py

Fixes common Alembic/Postgres failures automatically:
1) FK type mismatches to users.id (Integer -> String(36))
2) Missing Postgres ENUM types (pre-create Enum types before use)
3) Adding NOT NULL columns to existing tables (temporary server_default + drop default)

Usage (from backend/):
  python .\amodb\scripts\alembic_doctor.py heal
  python -m alembic -c .\amodb\alembic.ini upgrade head
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# -----------------------------
# Helpers: project discovery
# -----------------------------

def find_project_root(start: Path) -> Path:
    """
    Find the backend root that contains 'amodb/' as a folder.
    Works whether you run from backend/ or backend/amodb/.
    """
    cur = start.resolve()
    for _ in range(12):
        if (cur / "amodb").is_dir():
            return cur
        cur = cur.parent
    raise SystemExit("Could not locate project root (folder containing 'amodb/').")


def find_alembic_ini(root: Path) -> Path:
    ini = root / "amodb" / "alembic.ini"
    if not ini.exists():
        raise SystemExit(f"Could not find alembic.ini at: {ini}")
    return ini


def find_apps_dir(root: Path) -> Path:
    apps = root / "amodb" / "apps"
    if not apps.exists():
        raise SystemExit(f"Could not find apps directory at: {apps}")
    return apps


def find_versions_dir(root: Path) -> Path:
    versions = root / "amodb" / "alembic" / "versions"
    if not versions.exists():
        raise SystemExit(f"Could not find alembic versions directory at: {versions}")
    return versions


def backup_file(path: Path) -> Path:
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak_{ts}")
    shutil.copy2(path, bak)
    return bak


# -----------------------------
# Part 1: Fix users.id FK types
# -----------------------------

_USERS_FK_PATTERNS = [
    # Column(Integer, ForeignKey("users.id"...))
    (re.compile(r"(Column\s*\(\s*)Integer(\s*,\s*ForeignKey\s*\(\s*['\"]users\.id['\"])", re.MULTILINE), r"\1String(36)\2"),
    (re.compile(r"(Column\s*\(\s*)sa\.Integer\s*\(\s*\)(\s*,\s*sa\.ForeignKey\s*\(\s*['\"]users\.id['\"])", re.MULTILINE), r"\1sa.String(36)\2"),

    # sa.Column(sa.Integer(), sa.ForeignKey("users.id"...))
    (re.compile(r"(sa\.Column\s*\(\s*['\"][^'\"]+['\"]\s*,\s*)sa\.Integer\s*\(\s*\)(\s*,\s*sa\.ForeignKey\s*\(\s*['\"]users\.id['\"])", re.MULTILINE), r"\1sa.String(36)\2"),
    (re.compile(r"(Column\s*\(\s*['\"][^'\"]+['\"]\s*,\s*)Integer(\s*,\s*ForeignKey\s*\(\s*['\"]users\.id['\"])", re.MULTILINE), r"\1String(36)\2"),
]


def ensure_string_import_if_needed(text: str) -> str:
    """
    If file uses Column/String style (not sa.String) and doesn't import String,
    try to add String into 'from sqlalchemy import ...' imports.
    """
    if "String(" in text and "from sqlalchemy import" in text and " String" not in text:
        # naive but effective: inject String into the first sqlalchemy import list
        def repl(m: re.Match) -> str:
            imports = m.group(1)
            if "String" in imports:
                return m.group(0)
            # insert after Column if present, else at end
            if "Column" in imports:
                return f"from sqlalchemy import {imports}, String"
            return f"from sqlalchemy import {imports}, String"
        text = re.sub(r"from sqlalchemy import\s+([^\n]+)", repl, text, count=1)
    return text


def fix_users_fk_types(root: Path) -> List[Path]:
    apps_dir = find_apps_dir(root)
    changed: List[Path] = []

    for path in apps_dir.rglob("models.py"):
        src = path.read_text(encoding="utf-8")
        if "users.id" not in src:
            continue

        patched = src
        for rx, rep in _USERS_FK_PATTERNS:
            patched = rx.sub(rep, patched)

        patched = ensure_string_import_if_needed(patched)

        if patched != src:
            backup_file(path)
            path.write_text(patched, encoding="utf-8")
            changed.append(path)

    return changed


# -----------------------------
# Part 2: Patch Alembic revision
#   - Pre-create Postgres enums
#   - Add temporary server_default for NOT NULL add_column
# -----------------------------

def _extract_balanced(text: str, start: int) -> Optional[Tuple[str, int, int]]:
    """
    Given 'start' at the beginning of a call like 'op.add_column(' or 'sa.Enum(',
    return (call_text, start_index, end_index_exclusive).
    """
    i = text.find("(", start)
    if i == -1:
        return None
    depth = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:j + 1], start, j + 1
    return None


def _parse_enum_expr(expr: str) -> Optional[Tuple[str, List[str]]]:
    """
    expr: "sa.Enum('A','B', name='x')" -> (name, [values...])
    """
    try:
        tree = ast.parse("x=" + expr, mode="exec")
        call = tree.body[0].value
        if not isinstance(call, ast.Call):
            return None
        values = []
        for a in call.args:
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                values.append(a.value)
        name = None
        for kw in call.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                name = kw.value.value
        if name and values:
            return name, values
    except Exception:
        return None
    return None


def collect_enums(content: str) -> Dict[str, List[str]]:
    enums: Dict[str, List[str]] = {}
    idx = 0
    while True:
        m = re.search(r"\bsa\.Enum\s*\(", content[idx:])
        if not m:
            break
        start = idx + m.start()
        extracted = _extract_balanced(content, start)
        if not extracted:
            break
        call_text, _, end = extracted
        parsed = _parse_enum_expr(call_text.strip())
        if parsed:
            name, values = parsed
            enums.setdefault(name, values)
        idx = end
    return enums


def build_enum_precreate_block(enums: Dict[str, List[str]]) -> str:
    lines = [
        "    # AUTO-FIX: enum precreate (PostgreSQL requires CREATE TYPE before ALTER TABLE ADD COLUMN)",
        "    bind = op.get_bind()",
    ]
    for name, values in enums.items():
        vals = ", ".join(repr(v) for v in values)
        lines.append(f"    sa.Enum({vals}, name={name!r}).create(bind, checkfirst=True)")
    return "\n".join(lines) + "\n\n"


def insert_after_upgrade_def(content: str, block: str) -> Tuple[str, bool]:
    if "AUTO-FIX: enum precreate" in content:
        return content, False
    m = re.search(r"^\s*def\s+upgrade\s*\(.*?\)\s*(?:->\s*.*?\s*)?:\s*$", content, flags=re.MULTILINE)
    if not m:
        return content, False
    insert_pos = content.find("\n", m.end()) + 1
    if insert_pos <= 0:
        insert_pos = m.end()
    return content[:insert_pos] + block + content[insert_pos:], True


def _classify_type_node(node: ast.AST) -> Tuple[str, Optional[List[str]]]:
    """
    Returns: (kind, enum_values_if_any)
    kinds: enum|string|int|bool|datetime|date|other
    """
    def _name(n: ast.AST) -> str:
        if isinstance(n, ast.Attribute):
            return n.attr
        if isinstance(n, ast.Name):
            return n.id
        return ""

    if isinstance(node, ast.Call):
        nm = _name(node.func).lower()
        if nm == "enum":
            vals = []
            for a in node.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    vals.append(a.value)
            return "enum", vals
        if nm in ("string", "varchar", "text", "unicode", "unicodetext"):
            return "string", None
        if nm in ("integer", "biginteger", "smallinteger"):
            return "int", None
        if nm == "boolean":
            return "bool", None
        if nm in ("datetime", "timestamp"):
            return "datetime", None
        if nm == "date":
            return "date", None

    if isinstance(node, ast.Name):
        nm = node.id.lower()
        if nm == "enum":
            return "enum", []
        if nm in ("string", "varchar", "text", "unicode", "unicodetext"):
            return "string", None
        if nm in ("integer", "biginteger", "smallinteger"):
            return "int", None
        if nm == "boolean":
            return "bool", None
        if nm in ("datetime", "timestamp"):
            return "datetime", None
        if nm == "date":
            return "date", None

    return "other", None


def _default_expr_for_kind(kind: str, enum_vals: Optional[List[str]]) -> Optional[str]:
    if kind == "enum" and enum_vals:
        return repr(enum_vals[0])
    if kind == "string":
        return "''"
    if kind == "int":
        return "'0'"
    if kind == "bool":
        return "sa.text('false')"
    if kind == "datetime":
        return "sa.text('now()')"
    if kind == "date":
        return "sa.text('CURRENT_DATE')"
    return None


def patch_not_null_add_column_defaults(content: str) -> Tuple[str, List[Tuple[str, str]]]:
    """
    For op.add_column(<existing table>, sa.Column(... nullable=False)) with NO server_default,
    inject a temporary server_default and then drop it later.
    Returns patched_content, list_of_(table, col) patched.
    """
    patched = content
    patched_cols: List[Tuple[str, str]] = []

    # collect op.add_column calls
    calls: List[Tuple[str, int, int]] = []
    idx = 0
    while True:
        m = re.search(r"\bop\.add_column\s*\(", patched[idx:])
        if not m:
            break
        start = idx + m.start()
        extracted = _extract_balanced(patched, start)
        if not extracted:
            break
        call_text, s, e = extracted
        calls.append((call_text, s, e))
        idx = e

    # patch in reverse so indices stay stable
    for call_text, s, e in reversed(calls):
        try:
            tree = ast.parse("x=" + call_text, mode="exec")
            call = tree.body[0].value
        except Exception:
            continue
        if not isinstance(call, ast.Call) or len(call.args) < 2:
            continue

        table_node = call.args[0]
        col_node = call.args[1]
        if not (isinstance(table_node, ast.Constant) and isinstance(table_node.value, str)):
            continue
        if not isinstance(col_node, ast.Call):
            continue

        table = table_node.value
        colname = None
        if col_node.args and isinstance(col_node.args[0], ast.Constant) and isinstance(col_node.args[0].value, str):
            colname = col_node.args[0].value

        nullable_kw = next((kw for kw in col_node.keywords if kw.arg == "nullable"), None)
        server_default_kw = next((kw for kw in col_node.keywords if kw.arg == "server_default"), None)

        if not colname:
            continue
        if not nullable_kw or not (isinstance(nullable_kw.value, ast.Constant) and nullable_kw.value.value is False):
            continue
        if server_default_kw is not None:
            continue

        if len(col_node.args) < 2:
            continue
        type_node = col_node.args[1]
        kind, enum_vals = _classify_type_node(type_node)
        default_expr = _default_expr_for_kind(kind, enum_vals)
        if not default_expr:
            continue

        if "nullable=False" not in call_text:
            continue

        new_call_text = call_text.replace("nullable=False", f"server_default={default_expr}, nullable=False", 1)
        patched = patched[:s] + new_call_text + patched[e:]
        patched_cols.append((table, colname))

    if patched_cols and "AUTO-FIX: drop temporary defaults for NOT NULL add_column" not in patched:
        drop_lines = ["    # AUTO-FIX: drop temporary defaults for NOT NULL add_column"]
        for table, col in patched_cols:
            drop_lines.append(f"    op.alter_column({table!r}, {col!r}, server_default=None)")
        drop_block = "\n" + "\n".join(drop_lines) + "\n"

        m = re.search(r"^\s*def\s+downgrade\s*\(", patched, flags=re.MULTILINE)
        if m:
            patched = patched[:m.start()] + drop_block + patched[m.start():]
        else:
            # if no downgrade, just append (still inside upgrade if file ends after upgrade body)
            patched += drop_block

    return patched, patched_cols


def append_enum_drops(content: str, enums: Dict[str, List[str]]) -> Tuple[str, bool]:
    if not enums:
        return content, False
    if "AUTO-FIX: enum drop" in content:
        return content, False

    lines = ["", "    # AUTO-FIX: enum drop (best-effort on downgrade)", "    bind = op.get_bind()"]
    for name, values in enums.items():
        vals = ", ".join(repr(v) for v in values)
        lines.append(f"    sa.Enum({vals}, name={name!r}).drop(bind, checkfirst=True)")
    block = "\n".join(lines) + "\n"

    # safest: append to end of file (typically still inside downgrade body)
    return content + block, True


def patch_revision_file(revision_path: Path) -> None:
    src = revision_path.read_text(encoding="utf-8")
    enums = collect_enums(src)

    patched = src
    changed = False

    if enums:
        block = build_enum_precreate_block(enums)
        patched, did = insert_after_upgrade_def(patched, block)
        changed = changed or did

    patched, _patched_cols = patch_not_null_add_column_defaults(patched)
    changed = changed or (patched != src)

    if enums and "def downgrade" in patched:
        patched, did2 = append_enum_drops(patched, enums)
        changed = changed or did2

    if changed and patched != src:
        backup_file(revision_path)
        revision_path.write_text(patched, encoding="utf-8")


def latest_revision_file(root: Path) -> Path:
    versions = find_versions_dir(root)
    files = sorted(versions.glob("*.py"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise SystemExit(f"No revision files found in: {versions}")
    return files[0]


# -----------------------------
# Part 3: Run Alembic safely
# -----------------------------

def run_alembic_upgrade(root: Path) -> int:
    ini = find_alembic_ini(root)
    cmd = [sys.executable, "-m", "alembic", "-c", str(ini), "upgrade", "head"]
    print("Running:", " ".join(cmd))
    p = subprocess.run(cmd)
    return p.returncode


# -----------------------------
# CLI
# -----------------------------

def cmd_heal(args: argparse.Namespace) -> None:
    root = find_project_root(Path.cwd())

    changed_models = fix_users_fk_types(root)
    if changed_models:
        print("Patched users.id FK types in:")
        for p in changed_models:
            print("  -", p)
    else:
        print("No users.id FK type mismatches found.")

    rev = latest_revision_file(root) if args.revision is None else Path(args.revision).resolve()
    if not rev.exists():
        raise SystemExit(f"Revision not found: {rev}")

    patch_revision_file(rev)
    print(f"Patched revision: {rev}")

    rc = run_alembic_upgrade(root)
    if rc != 0:
        raise SystemExit(rc)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    heal = sub.add_parser("heal", help="Fix models + patch latest revision + run alembic upgrade head")
    heal.add_argument("--revision", help="Patch a specific revision file instead of latest", default=None)
    heal.set_defaults(func=cmd_heal)

    ns = ap.parse_args()
    ns.func(ns)


if __name__ == "__main__":
    main()
