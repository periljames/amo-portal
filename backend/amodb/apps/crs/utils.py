# backend/amodb/apps/crs/utils.py
from datetime import datetime


def generate_crs_serial(crs_id: int) -> str:
    """
    Generate a human-readable CRS serial number based on the DB id.

    Example: CRS-2025-000123
    """
    year = datetime.utcnow().year
    return f"CRS-{year}-{crs_id:06d}"
