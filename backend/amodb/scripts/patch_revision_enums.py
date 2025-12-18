# amodb/scripts/patch_revision_enums.py
from __future__ import annotations

import argparse
import re
from pathlib import Path


UPGRADE_RE = re.compile(r"^def\s+upgrade\s*\([^)]*\)\s*(->\s*[^:]+)?\s*:\s*$", re.M)


def _find_call_span(src: str, start: int) -> tuple[int, int]:
    """
    Given src and index pointing at start of 'sa.Enum(' (the 's'), return (call_start, call_end_exclusive).
    Parses parentheses with basic string handling.
    """
    i = start
    if not src.startswith("sa.Enum(", i):
        raise ValueError("start does not point to sa.Enum(")

    # Move to first '('
    i = i + len("sa.Enum")
    if src[i] != "(":
        raise ValueError("expected '(' after sa.Enum")
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
                    return call_start, j + 1  # exclusive
        j += 1

    raise ValueError("Unclosed parentheses while parsing sa.Enum(...) call")


def _extract_args(call_text: str) -> str:
    # call_text like "sa.Enum(...)" -> return inside of parentheses
    assert call_text.startswith("sa.Enum(") and call_text.endswith(")")
    return call_text[len("sa.Enum(") : -1]


def _has_kw(args_text: str, kw: str) -> bool:
    return re.search(rf"\b{re.escape(kw)}\s*=", args_text) is not None


def _strip_kw(args_text: str, kw: str) -> str:
    # remove ", kw=..." or "kw=..." occurrences (best-effort, generated code is simple)
    args_text = re.sub(rf",\s*{re.escape(kw)}\s*=\s*[^,)\n]+", "", args_text)
    args_text = re.sub(rf"^\s*{re.escape(kw)}\s*=\s*[^,)\n]+\s*,\s*", "", args_text)
    args_text = re.sub(rf"\s*{re.escape(kw)}\s*=\s*[^,)\n]+\s*$", "", args_text)
    return args_text.strip()


def patch_revision(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")

    m = UPGRADE_RE.search(src)
    if not m:
        raise SystemExit(f"Could not find upgrade() in: {path}")

    # Ensure postgresql import exists
    if "from sqlalchemy.dialects import postgresql" not in src:
        # Insert after "import sqlalchemy as sa" if present, else after alembic import
        insert_after = src.find("import sqlalchemy as sa")
        if insert_after != -1:
            line_end = src.find("\n", insert_after)
            src = src[: line_end + 1] + "from sqlalchemy.dialects import postgresql\n" + src[line_end + 1 :]
        else:
            alembic_op = src.find("from alembic import op")
            if alembic_op != -1:
                line_end = src.find("\n", alembic_op)
                src = src[: line_end + 1] + "from sqlalchemy.dialects import postgresql\n" + src[line_end + 1 :]
            else:
                src = "from sqlalchemy.dialects import postgresql\n" + src

    # Find all sa.Enum(...) calls and collect enum definitions (by name=)
    enums: dict[str, str] = {}
    idx = 0
    spans: list[tuple[int, int, str, str]] = []

    while True:
        pos = src.find("sa.Enum(", idx)
        if pos == -1:
            break
        call_start, call_end = _find_call_span(src, pos)
        call_text = src[call_start:call_end]
        args_text = _extract_args(call_text)

        name_m = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", args_text)
        if name_m:
            enum_name = name_m.group(1)
            if enum_name not in enums:
                enums[enum_name] = args_text  # original args (no create_type injected yet)
        spans.append((call_start, call_end, call_text, args_text))
        idx = call_end

    changed = False

    # Replace sa.Enum(...) -> postgresql.ENUM(..., create_type=False)
    # Do replacements back-to-front so indices don't shift
    for call_start, call_end, call_text, args_text in reversed(spans):
        if not _has_kw(args_text, "name"):
            continue  # can't safely manage unnamed enums
        rep_args = args_text
        if not _has_kw(rep_args, "create_type"):
            rep_args = rep_args.strip()
            if rep_args.endswith(","):
                rep_args = rep_args[:-1]
            rep_args = rep_args + ", create_type=False"
        replacement = f"postgresql.ENUM({rep_args})"
        if replacement != call_text:
            src = src[:call_start] + replacement + src[call_end:]
            changed = True

    # Inject precreate block (idempotent) once
    sentinel = "# AUTO-FIX: enum precreate (checkfirst)"
    if enums and sentinel not in src:
        # Insert right after the upgrade() signature line
        sig_line_end = src.find("\n", m.start())
        sig_line_end = src.find("\n", sig_line_end + 1)  # end of the def line
        if sig_line_end == -1:
            sig_line_end = len(src)

        # Determine indentation inside function (assume 4 spaces)
        indent = " " * 4

        # Build precreate lines
        pre = [f"{indent}{sentinel}", f"{indent}bind = op.get_bind()"]
        for enum_name in sorted(enums.keys()):
            args0 = enums[enum_name]
            # Precreate should NOT include create_type=False (we use checkfirst anyway, but keep it clean)
            args0 = _strip_kw(args0, "create_type")
            pre.append(f"{indent}postgresql.ENUM({args0}).create(bind, checkfirst=True)")
        pre_block = "\n" + "\n".join(pre) + "\n"

        src = src[:sig_line_end] + pre_block + src[sig_line_end:]
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
        changed = patch_revision(path)
        print(f"{'Patched' if changed else 'No change'}: {path}")
        any_changed = any_changed or changed

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
