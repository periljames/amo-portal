from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


class IntervalParseError(ValueError):
    pass


COUNTER_ALIASES = {
    "FH": "FH",
    "FLIGHT HOUR": "FH",
    "FLIGHT HOURS": "FH",
    "FC": "FC",
    "FLIGHT CYCLE": "FC",
    "FLIGHT CYCLES": "FC",
    "EH": "EH",
    "ENGINE HOUR": "EH",
    "ENGINE HOURS": "EH",
    "APUH": "APUH",
    "APU HOUR": "APUH",
    "APU HOURS": "APUH",
    "LANDING": "LANDINGS",
    "LANDINGS": "LANDINGS",
    "DY": "DY",
    "DAY": "DY",
    "DAYS": "DY",
    "MO": "MO",
    "MONTH": "MO",
    "MONTHS": "MO",
    "YR": "YR",
    "YEAR": "YR",
    "YEARS": "YR",
    "START": "STARTS",
    "STARTS": "STARTS",
}

PHASE_ALIASES = {
    "T": "THRESHOLD",
    "THRESHOLD": "THRESHOLD",
    "II": "INITIAL",
    "INITIAL": "INITIAL",
    "INITIAL INTERVAL": "INITIAL",
    "RC": "REPEAT_CUT_IN",
    "REPEAT CUT-IN": "REPEAT_CUT_IN",
    "REPEAT CUT IN": "REPEAT_CUT_IN",
    "R": "REPEAT",
    "REPEAT": "REPEAT",
}

NUMBER = r"(?P<value>\d+(?:\.\d+)?)"
UNIT = r"(?P<unit>APUH|APU\s+HOURS?|EH|ENGINE\s+HOURS?|FH|FLIGHT\s+HOURS?|FC|FLIGHT\s+CYCLES?|LANDINGS?|DY|DAYS?|MO|MONTHS?|YR|YEARS?|STARTS?)"
LIMIT_RE = re.compile(rf"^\s*{NUMBER}\s*{UNIT}\s*$", re.IGNORECASE)
PHASE_TOKEN_RE = re.compile(
    rf"(?:^|[;,]\s*)\b(?P<phase>THRESHOLD|INITIAL\s+INTERVAL|INITIAL|REPEAT\s+CUT[- ]IN|REPEAT|II|RC|T|R)\b\s*[:=-]?\s*(?P<limit>{NUMBER}\s*{UNIT})",
    re.IGNORECASE,
)


def _exact_number(value: str) -> str | int:
    try:
        decimal = Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - protected by regex
        raise IntervalParseError(f"Invalid controlled interval value: {value}") from exc
    if not decimal.is_finite() or decimal <= 0:
        raise IntervalParseError("Controlled interval values must be positive")
    if decimal == decimal.to_integral_value():
        return int(decimal)
    return format(decimal, "f")


def _parse_limit(text: str) -> dict[str, Any]:
    match = LIMIT_RE.match(text.strip())
    if not match:
        raise IntervalParseError(f"Unsupported interval limit: {text.strip()}")
    raw_unit = " ".join(match.group("unit").upper().split())
    counter = COUNTER_ALIASES.get(raw_unit)
    if not counter:
        raise IntervalParseError(f"Unsupported interval counter: {raw_unit}")
    return {"counter": counter, "value": _exact_number(match.group("value"))}


def _simple_group(text: str, *, phase: str = "INTERVAL") -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", text.strip())
    parts = [part.strip() for part in re.split(r"\s+OR\s+", normalized, flags=re.IGNORECASE)]
    if len(parts) == 1:
        return {"phase": phase, "mode": "SINGLE", "limits": [_parse_limit(parts[0])]}
    if any(not part for part in parts):
        raise IntervalParseError(f"Incomplete whichever-first interval: {text}")
    return {
        "phase": phase,
        "mode": "WHICHEVER_FIRST",
        "limits": [_parse_limit(part) for part in parts],
    }


def parse_interval_text(raw: str) -> dict[str, Any]:
    """Parse controlled OEM interval wording without inventing missing semantics.

    This intentionally handles common explicit MPD/EMP forms only. Anything
    ambiguous raises IntervalParseError and must remain in raw_interval_text for
    engineering review rather than being guessed into a compliance clock.
    """

    text = " ".join(raw.replace("\u2212", "-").replace("\xa0", " ").split())
    if not text:
        raise IntervalParseError("Interval text is empty")
    upper = text.upper()
    if "OPPORTUNITY" in upper:
        return {
            "schema": "MPD_INTERVAL_V1",
            "groups": [
                {
                    "phase": "INTERVAL",
                    "mode": "OPPORTUNITY",
                    "reference": text,
                }
            ],
            "raw": raw,
        }

    phase_matches = list(PHASE_TOKEN_RE.finditer(text))
    if phase_matches:
        groups: list[dict[str, Any]] = []
        consumed: list[tuple[int, int]] = []
        for match in phase_matches:
            phase_key = " ".join(match.group("phase").upper().replace("-", " ").split())
            phase = PHASE_ALIASES.get(phase_key)
            if not phase:
                raise IntervalParseError(f"Unsupported interval phase: {match.group('phase')}")
            groups.append(_simple_group(match.group("limit"), phase=phase))
            consumed.append(match.span())
        residue = text
        for start, end in reversed(consumed):
            residue = residue[:start] + " " + residue[end:]
        residue = re.sub(r"[\s,;:/-]+", " ", residue).strip()
        if residue and not re.fullmatch(r"(?:NOTE\s*\d+|MRB\s+SYS\s+NOTE\s*\d+|AND|OR|/)*", residue, re.IGNORECASE):
            raise IntervalParseError(f"Unparsed interval wording remains: {residue}")
        return {"schema": "MPD_INTERVAL_V1", "groups": groups, "raw": raw}

    # Strip common source-note suffixes without treating the note as an interval.
    simple_text = re.sub(
        r"\s+(?:MRB\s+SYS\s+NOTE|NOTE)\s*\d+\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    group = _simple_group(simple_text)
    return {"schema": "MPD_INTERVAL_V1", "groups": [group], "raw": raw}
