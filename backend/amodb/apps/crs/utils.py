# backend/amodb/apps/crs/utils.py
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from . import models as crs_models

# Mapping from logical check type to the single-character code in YYXNNN
CHECK_TYPE_CODE_MAP = {
    "200HR": "2",  # 200-hour checks
    "A": "A",      # A-check
    "C": "C",      # C-check
}


def infer_check_type(
    next_maintenance_due: Optional[str],
) -> Optional[str]:
    """
    Try to infer the check type (200HR / A / C) from the 'next_maintenance_due'
    text that the user enters, e.g.:
        "A CHECK", "A-CHECK", "A check"
        "C CHECK", "C-CHECK"
        "200HR", "200 HR", "200 HRS CHECK"

    Returns:
        "A", "C", "200HR", or None if it cannot be inferred.
    """
    if not next_maintenance_due:
        return None

    text = next_maintenance_due.upper().replace("-", " ").strip()

    # Normalise multiple spaces
    text = " ".join(text.split())

    # 200-hour
    if "200" in text and "HR" in text:
        return "200HR"

    # A-check
    if text.startswith("A ") or " A CHECK" in text or text == "A CHECK":
        return "A"

    # C-check
    if text.startswith("C ") or " C CHECK" in text or text == "C CHECK":
        return "C"

    return None


def generate_crs_serial(
    db: Session,
    check_type: str,
    issue_date: date,
) -> str:
    """
    Generate a CRS serial in the format YYXNNN, where:

      - YY = last two digits of the year (same scheme as W/O, e.g. 25)
      - X  = check-type code ('2' for 200HR, 'A' for A-check, 'C' for C-check)
      - NNN = sequential number per (year, check_type), zero-padded to 3 digits.

    Only 200HR / A / C are supported. Anything else should never produce a CRS.
    """
    if check_type not in CHECK_TYPE_CODE_MAP:
        raise ValueError(
            f"Unsupported CRS check_type '{check_type}'. "
            "CRS can only be created for 200HR, A-check, or C-check work orders."
        )

    code = CHECK_TYPE_CODE_MAP[check_type]

    year_suffix = issue_date.year % 100
    prefix = f"{year_suffix:02d}{code}"  # e.g. '252' or '25A' or '25C'

    # Find the highest existing serial for this year+check_type
    last = (
        db.query(crs_models.CRS.crs_serial)
        .filter(crs_models.CRS.crs_serial.like(f"{prefix}%"))
        .order_by(crs_models.CRS.crs_serial.desc())
        .first()
    )

    if last:
        try:
            last_seq = int(last[0][-3:])
        except ValueError:
            # In case of legacy bad data, restart numbering cleanly
            last_seq = 0
    else:
        last_seq = 0

    if last_seq >= 999:
        raise ValueError(
            f"CRS sequence exhausted for year {year_suffix:02d} / type {check_type}."
        )

    next_seq = last_seq + 1
    return f"{prefix}{next_seq:03d}"
