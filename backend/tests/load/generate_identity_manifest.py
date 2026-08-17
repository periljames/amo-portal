"""Build the k6 identity manifest from pre-provisioned test users.

This deliberately does not create production users. Feed it a CSV containing
tenant_id,user_id,token exported from the isolated performance environment.
"""
from __future__ import annotations

import csv
import json
import sys

source, destination = sys.argv[1:3]
with open(source, newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))
if len(rows) < 20_000 or len({row["tenant_id"] for row in rows}) < 20:
    raise SystemExit("Input must contain >=20,000 identities across >=20 tenants")
with open(destination, "w", encoding="utf-8") as handle:
    json.dump(rows, handle, separators=(",", ":"))
