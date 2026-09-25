#!/usr/bin/env bash
# Run as postgres. This is a logical recovery copy, not WAL/PITR or off-host backup.
set -euo pipefail
umask 077
ROOT="${AMO_BACKUP_ROOT:-/var/backups/amo-postgres}"
mkdir -p "$ROOT"
exec 9>"$ROOT/.backup.lock"
flock -n 9 || exit 0
# Leave headroom for PostgreSQL; failure is visible in systemd.
AVAILABLE=$(df -Pk "$ROOT" | awk 'NR==2 {print $4}')
if (( AVAILABLE < 1048576 )); then
  echo "Insufficient backup disk headroom" >&2
  exit 1
fi
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
STAGE=$(mktemp -d "$ROOT/.partial-$STAMP-XXXXXX")
pg_dump --dbname=amodb --format=custom --file="$STAGE/amodb.dump"
pg_dumpall --globals-only > "$STAGE/globals.sql"
pg_restore --list "$STAGE/amodb.dump" > "$STAGE/contents.txt"
(cd "$STAGE" && sha256sum amodb.dump globals.sql contents.txt > SHA256SUMS)
printf '%s\n' 'AMO_PG_BACKUP_V1' > "$STAGE/.amo-backup-complete"
mv -T "$STAGE" "$ROOT/$STAMP"
echo "Verified archive structure and checksums: $ROOT/$STAMP"
# Keep seven days at the six-hour cadence. Only this script's marked completed
# directories qualify; unknown directories and incomplete backups are untouched.
python3 - "$ROOT" <<'PY'
from pathlib import Path
import re
import shutil
import sys

root = Path(sys.argv[1]).resolve()
owned = []
for path in root.iterdir():
    if path.is_symlink() or not path.is_dir() or not re.fullmatch(r'20\d{6}T\d{6}Z', path.name):
        continue
    marker = path / '.amo-backup-complete'
    if path.resolve().parent == root and marker.is_file() and marker.read_text().strip() == 'AMO_PG_BACKUP_V1':
        owned.append(path)
for path in sorted(owned)[:-28]:
    shutil.rmtree(path)
PY
