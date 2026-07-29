from pathlib import Path

path = Path('.github/scripts/fix_workforce_active_users_default_day.py')
text = path.read_text(encoding='utf-8')
old = '''from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected block not found in {path}: {old[:120]!r}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")
'''
new = '''from pathlib import Path
import re


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if new in text:
        return
    if old in text:
        file_path.write_text(text.replace(old, new, 1), encoding="utf-8")
        return
    parts = re.split(r"(\\s+)", old)
    pattern = "".join(r"\\s+" if part.isspace() else re.escape(part) for part in parts if part)
    match = re.search(pattern, text)
    if match is None:
        raise RuntimeError(f"Expected block not found in {path}: {old[:120]!r}")
    file_path.write_text(text[:match.start()] + new + text[match.end():], encoding="utf-8")
'''
if old not in text:
    raise RuntimeError('Original replace_once helper not found')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('Prepared whitespace-tolerant PR377 patcher.')
