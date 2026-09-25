#!/usr/bin/env python3
"""Restore the latest archive to a uniquely named disposable database.

Run as postgres on the backup source. Requires free space for one additional
database. Never replaces or drops the source database.
"""
from pathlib import Path
import subprocess
import uuid

root = Path('/var/backups/amo-postgres')
latest = sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith('20'))[-1]
name = 'amo_restore_' + uuid.uuid4().hex[:12]
created = False
try:
    subprocess.run(['createdb', name], check=True)
    created = True
    subprocess.run(['pg_restore', '--exit-on-error', '--dbname=' + name, str(latest / 'amodb.dump')], check=True)
    result = subprocess.check_output(['psql', '-d', name, '-Atc',
        "select count(*) from pg_tables where schemaname='public'; select count(*) from users;"], text=True)
    counts = [int(value) for value in result.splitlines()]
    if len(counts) != 2 or counts[0] == 0:
        raise RuntimeError('Restored schema validation failed')
    print(f'RESTORE VERIFIED archive={latest.name} tables={counts[0]} users={counts[1]}', flush=True)
finally:
    if created:
        subprocess.run(['dropdb', name], check=True)
