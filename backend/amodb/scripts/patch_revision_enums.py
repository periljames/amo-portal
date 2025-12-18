# amodb/scripts/patch_revision_enums.py
from __future__ import annotations

import argparse
import re
from pathlib import Path

UPGRADE_LINE_RE = re.compile(r"^\s*def\s+upgrade\s*\(", re.M)
SENTINEL = "# AUTO-FIX: enum precreate (checkfirst)"

def _detect_newline(src: str) -> str:
    return "\r\n" if "\r\n" in src else "\n"

def _ensure_postgresql_import(src: str) -> tuple[str, bool]:
    """
    Ensure: from sqlalchemy.dialects import postgresql
    Insert after 'import sqlalchemy as sa' if present, else after 'from alembic import op',
    else after __future__ import block, else at top.
    """
    if "from sqlalchemy.dialects import postgresql" in src:
        return src, False

    nl = _detect_newline(src)
    lines = src.splitlines(True)

    insert_at = None

    # after "import sqlalchemy as sa"
    for i, ln in enumerate(lines):
        if ln.strip() == "import sqlalchemy as sa":
            insert_at = i + 1
            break

    # else after "from alembic import op"
    if insert_at is None:
        for i, ln in enumerate(lines):
            if ln.strip() == "from alembic import op":
                insert_at = i + 1
                break

    # else after __future__ imports
    if insert_at is None:
        insert_at = 0
        for i, ln in enumerate(lines):
            if ln.startswith("from __future__ import"):
                insert_at = i + 1

    lines.insert(insert_at, f"from sqlalchemy.dialects import postgresql{nl}")
    return "".join(lines), True

def _find_call_span(src: str, start: int, prefix: str) -> tuple[int, int]:
    """
    Given src and index pointing at start of '<prefix>Enum(' (the 'E'),
    return (call_start, call_end_exclusive). Parses parentheses with basic string handling.
    prefix examples: 'sa.' or 'sqlalchemy.'
    """
    token = f"{prefix}Enum("
    if not src.startswith(token, start):
        raise ValueError(f"start does not point to {token}")

    i = start + len(prefix) + len("Enum")
    if src[i] != "(":
        raise ValueError("expected '(' after Enum")

    depth = 0
    in_str = None
    esc = False

    call_start = start
    j = i
    while j < len(src):
        ch = src[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_str:
                in_str = None
        else:
            if ch in ("'", '"'):
                in_str = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return call_start, j + 1
        j += 1

    raise ValueError("Unclosed parentheses while parsing Enum(...) call")

def _extract_args(call_text: str, prefix: str) -> str:
    # call_text like "sa.Enum(...)" or "sqlalchemy.Enum(...)" -> return inside parentheses
    token = f"{prefix}Enum("
    assert call_text.startswith(token) and call_text.endswith(")")
    return call_text[len(token) : -1]

def _has_kw(args_text: str, kw: str) -> bool:
    return re.search(rf"\b{re.escape(kw)}\s*=", args_text) is not None

def _strip_kw(args_text: str, kw: str) -> str:
    # best-effort removal for generated code
    args_text = re.sub(rf",\s*{re.escape(kw)}\s*=\s*[^,)\n]+", "", args_text)
    args_text = re.sub(rf"^\s*{re.escape(kw)}\s*=\s*[^,)\n]+\s*,\s*", "", args_text)
    args_text = re.sub(rf"\s*{re.escape(kw)}\s*=\s*[^,)\n]+\s*$", "", args_text)
    return args_text.strip()

def _fix_stray_indented_autofix_before_upgrade(src: str) -> tuple[str, bool]:
    """
    If an AUTO-FIX block (or bind/postgresql.ENUM.create lines) were accidentally inserted
    *above* def upgrade(), remove them from top-level (prevents IndentationError).
    """
    nl = _detect_newline(src)
    lines = src.splitlines(True)

    # locate upgrade def line index
    u_idx = None
    for i, ln in enumerate(lines):
        if UPGRADE_LINE_RE.match(ln):
            u_idx = i
            break
    if u_idx is None:
        raise SystemExit("Could not find upgrade() in revision file")

    pre = lines[:u_idx]
    post = lines[u_idx:]

    def is_stray(ln: str) -> bool:
        if not ln.startswith("    "):
            return False
        s = ln.strip()
        return (
            s.startswith(SENTINEL)
            or s.startswith("bind = op.get_bind()")
            or (s.startswith("postgresql.ENUM(") and ".create(" in s)
        )

    new_pre = []
    removed_any = False
    for ln in pre:
        if is_stray(ln):
            removed_any = True
        else:
            new_pre.append(ln)

    if not removed_any:
        return src, False

    return "".join(new_pre + post), True

def patch_revision(path: Path) -> bool:
    src0 = path.read_text(encoding="utf-8")
    nl = _detect_newline(src0)

    changed = False

    # 0) If your last run broke the file, clean stray indented AUTO-FIX lines above upgrade()
    src, did = _fix_stray_indented_autofix_before_upgrade(src0)
    changed |= did

    # 1) Ensure postgresql import exists
    src, did = _ensure_postgresql_import(src)
    changed |= did

    # 2) Find all Enum calls (sa.Enum / sqlalchemy.Enum), collect by name=, and patch to postgresql.ENUM(..., create_type=False)
    enums: dict[str, str] = {}
    spans: list[tuple[int, int, str, str]] = []  # (start,end,call_text,args_text)

    def scan(prefix: str) -> None:
        nonlocal src, enums, spans
        token = f"{prefix}Enum("
        idx = 0
        while True:
            pos = src.find(token, idx)
            if pos == -1:
                break
            cs, ce = _find_call_span(src, pos, prefix)
            call_text = src[cs:ce]
            args_text = _extract_args(call_text, prefix)

            name_m = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", args_text)
            if name_m:
                enum_name = name_m.group(1)
                if enum_name not in enums:
                    enums[enum_name] = args_text

            spans.append((cs, ce, call_text, args_text))
            idx = ce

    scan("sa.")
    scan("sqlalchemy.")

    # replace back-to-front so indices don't shift
    for cs, ce, call_text, args_text in sorted(spans, key=lambda x: x[0], reverse=True):
        if not _has_kw(args_text, "name"):
            continue

        rep_args = args_text.strip()
        if not _has_kw(rep_args, "create_type"):
            if rep_args.endswith(","):
                rep_args = rep_args[:-1]
            rep_args = rep_args + ", create_type=False"

        replacement = f"postgresql.ENUM({rep_args})"
        if replacement != call_text:
            src = src[:cs] + replacement + src[ce:]
            changed = True

    # 3) Insert idempotent precreate block inside upgrade(), right after the def line
    if enums and SENTINEL not in src:
        lines = src.splitlines(True)

        u_idx = None
        for i, ln in enumerate(lines):
            if UPGRADE_LINE_RE.match(ln):
                u_idx = i
                break
        if u_idx is None:
            raise SystemExit(f"Could not find upgrade() in: {path}")

        indent = " " * 4
        pre = [
            f"{indent}{SENTINEL}{nl}",
            f"{indent}bind = op.get_bind(){nl}",
        ]
        for enum_name in sorted(enums.keys()):
            args0 = _strip_kw(enums[enum_name], "create_type")
            pre.append(f"{indent}postgresql.ENUM({args0}).create(bind, checkfirst=True){nl}")

        # insert immediately after def upgrade line
        lines[u_idx + 1:u_idx + 1] = pre
        src = "".join(lines)
        changed = True

    if changed:
        path.write_text(src, encoding="utf-8")

    return changed

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("revision", nargs="+", help="Path(s) to alembic revision .py file(s)")
    args = ap.parse_args()

    any_changed = False
    for p in args.revision:
        path = Path(p).resolve()
        if not path.exists():
            raise SystemExit(f"Not found: {path}")
        did = patch_revision(path)
        print(f"{'Patched' if did else 'No change'}: {path}")
        any_changed = any_changed or did

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
