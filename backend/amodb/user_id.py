from typing import Iterable


def _base_lastname_style(first_name: str, last_name: str) -> str:
    first_name = (first_name or "").strip().upper()
    last_name = (last_name or "").strip().upper()

    if not last_name and not first_name:
        return "USER"

    # Start with up to 4 letters from last name
    base = last_name[:4]
    # If last name too short, pad with first name letters
    needed = 4 - len(base)
    if needed > 0:
        base += first_name[:needed]

    return base or "USER"


def _base_two_two_style(first_name: str, last_name: str) -> str:
    first_name = (first_name or "").strip().upper()
    last_name = (last_name or "").strip().upper()

    if len(first_name) >= 2 and len(last_name) >= 2:
        return first_name[:2] + last_name[:2]
    return _base_lastname_style(first_name, last_name)


def generate_user_id(
    first_name: str,
    last_name: str,
    existing_ids: Iterable[str],
    prefer_style: str = "LAST4",
) -> str:
    """
    Generate a unique employee/user ID.

    Rules:
    - Default base = first 4 letters of last name (LAST4 style),
      padded with first name if needed.
    - Alternative base = first 2 of first name + first 2 of last name (2+2 style).
    - Suffix: two-digit integer starting at 01, never reused.

    `existing_ids` should contain all current user_code values.
    """
    existing = {e.upper() for e in existing_ids if e}

    if prefer_style.upper() == "BOTH2":
        base = _base_two_two_style(first_name, last_name)
    else:
        base = _base_lastname_style(first_name, last_name)

    base = base.upper()

    counter = 1
    while True:
        suffix = f"{counter:02d}"
        candidate = f"{base}{suffix}"
        if candidate not in existing:
            return candidate
        counter += 1
