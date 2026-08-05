from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "backend/amodb/apps/reliability/workpack_integration.py"
text = path.read_text(encoding="utf-8")

old = "from datetime import date, datetime, time, timezone\n"
new = "from datetime import date, datetime, time, timedelta, timezone\n"
if text.count(old) != 1:
    raise RuntimeError("datetime import anchor changed")
text = text.replace(old, new, 1)

anchor = '''def _date_as_utc(value: Optional[date]) -> Optional[datetime]:
    if value is None:
        return None
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


'''
addition = '''def _date_as_utc(value: Optional[date]) -> Optional[datetime]:
    if value is None:
        return None
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


def _sync_cursor(last_success_at: Optional[datetime]) -> datetime:
    """Overlap internal sync windows so records committed near a cutoff cannot be lost."""
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    resolved = _as_utc(last_success_at)
    return max(resolved - timedelta(minutes=5), epoch) if resolved else epoch


'''
if text.count(anchor) != 1:
    raise RuntimeError("sync cursor insertion anchor changed")
text = text.replace(anchor, addition, 1)

old = '''    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    builders = {
'''
new = '''    builders = {
'''
if text.count(old) != 1:
    raise RuntimeError("epoch anchor changed")
text = text.replace(old, new, 1)

old = '''        source = sources[code]
        cursor = _as_utc(source.last_success_at) or epoch
        records = builder(db, amo_id=amo_id, cursor=cursor)
'''
new = '''        source = sources[code]
        cursor = _sync_cursor(source.last_success_at)
        records = builder(db, amo_id=amo_id, cursor=cursor)
'''
if text.count(old) != 1:
    raise RuntimeError("cursor use anchor changed")
text = text.replace(old, new, 1)

old = '''        else:
            source.next_poll_at = datetime.now(timezone.utc)
            db.commit()
'''
new = '''        else:
            now = datetime.now(timezone.utc)
            source.last_success_at = now
            source.next_poll_at = now + timedelta(minutes=max(source.poll_interval_minutes or 60, 5))
            db.commit()
'''
if text.count(old) != 1:
    raise RuntimeError("no-record schedule anchor changed")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")

test_path = ROOT / "backend/amodb/apps/reliability/tests/test_workpack_integration.py"
test = test_path.read_text(encoding="utf-8")
old = "from datetime import datetime, timezone\n"
new = "from datetime import datetime, timedelta, timezone\n"
if test.count(old) != 1:
    raise RuntimeError("test import anchor changed")
test = test.replace(old, new, 1)

test += '''\n\ndef test_sync_cursor_overlaps_last_success_without_crossing_epoch():\n    last_success = datetime(2026, 8, 5, 7, 0, tzinfo=timezone.utc)\n    assert integration._sync_cursor(last_success) == last_success - timedelta(minutes=5)\n    assert integration._sync_cursor(None) == datetime(1970, 1, 1, tzinfo=timezone.utc)\n'''
test_path.write_text(test, encoding="utf-8")

(ROOT / "scripts/harden_reliability_workpack_sync.py").unlink(missing_ok=True)
(ROOT / ".github/workflows/reliability-workpack-sync-hardening.yml").unlink(missing_ok=True)
