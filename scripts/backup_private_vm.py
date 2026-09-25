"""Copy and checksum the VM's latest logical backup using a restricted SSH key.

No database or SSH passwords are stored by this script. Files are private to
the Windows account running it. Keep the VM's backup timer enabled.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
from pathlib import Path
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", default=str(Path(os.environ["LOCALAPPDATA"]) / "AMO-Portal/backups/postgres"))
    args = parser.parse_args()
    root = Path(args.destination)
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < 1024 ** 3:
        raise RuntimeError("Less than 1 GiB backup disk headroom")
    key = Path(os.environ["LOCALAPPDATA"]) / "AMO-Portal" / "recovery" / "backup_ed25519"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    partial = root / (stamp + ".partial")
    with partial.open("xb") as output:
        subprocess.run([
            "ssh", "-T", "-i", str(key), "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "HostKeyAlias=megatron", "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
            "postgres@192.168.72.10",
        ], stdout=output, check=True, timeout=600)
        output.flush()
        os.fsync(output.fileno())
    # Verify in-place without extracting potentially unsafe archive paths.
    with tarfile.open(partial) as archive:
        expected = {"amodb.dump", "globals.sql", "contents.txt", "SHA256SUMS"}
        members = archive.getmembers()
        if len(members) != 4 or {m.name for m in members} != expected or not all(m.isfile() for m in members):
            raise RuntimeError("Unexpected backup archive structure")
        manifest = archive.extractfile("SHA256SUMS").read().decode("ascii")
        checked = set()
        for line in manifest.splitlines():
            digest, name = line.split(maxsplit=1)
            if name not in expected - {"SHA256SUMS"} or name in checked:
                raise RuntimeError("Unexpected checksum entry")
            with archive.extractfile(name) as source:
                actual = hashlib.file_digest(source, "sha256").hexdigest()
            if actual != digest:
                raise RuntimeError("Backup checksum mismatch")
            checked.add(name)
        if checked != expected - {"SHA256SUMS"}:
            raise RuntimeError("Incomplete checksum manifest")
    destination = partial.with_suffix(".tar")
    partial.rename(destination)
    print(f"Verified backup: {destination}")
    # Bound local storage to 56 verified copies (14 days at four per day).
    # Only filenames emitted by this script in this exact directory qualify.
    owned = sorted(path for path in root.iterdir()
                   if path.is_file() and not path.is_symlink()
                   and re.fullmatch(r"20\d{6}T\d{12}Z\.tar", path.name)
                   and path.resolve().parent == root.resolve())
    for path in owned[:-56]:
        path.unlink()


if __name__ == "__main__":
    main()
