"""Server-owned identifiers for the shared tenant supplier master."""
from uuid import uuid4


def new_supplier_code() -> str:
    # No client-supplied counter and no cross-worker read/increment race.
    # The supplier master unique constraint remains authoritative.
    return f"VND-{uuid4().hex[:12].upper()}"
