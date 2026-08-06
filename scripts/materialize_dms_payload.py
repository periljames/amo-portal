"""Materialize the reviewed DMS source payload committed in split base64 parts."""
from __future__ import annotations

import base64
import hashlib
import io
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / ".github" / "dms-payload"
EXPECTED = "3c758eb5391fabca86769d960960aa7c0d4d31f8be34aab5cbc8e1db147db64a"


def main() -> None:
    encoded = b"".join(path.read_bytes() for path in sorted(PARTS.glob("part-*")))
    archive = base64.b64decode(encoded, validate=True)
    actual = hashlib.sha256(archive).hexdigest()
    if actual != EXPECTED:
        raise SystemExit(f"payload checksum mismatch: {actual}")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        for member in bundle.getmembers():
            target = (ROOT / member.name).resolve()
            if ROOT not in target.parents and target != ROOT:
                raise SystemExit(f"unsafe payload member: {member.name}")
        bundle.extractall(ROOT, filter="data")


if __name__ == "__main__":
    main()
