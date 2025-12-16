# backend/amodb/apps/quality/enums.py
from __future__ import annotations

import enum


class QMSDomain(str, enum.Enum):
    AMO = "AMO"
    AOC = "AOC"
    CORPORATE = "CORPORATE"


class QMSDocType(str, enum.Enum):
    MANUAL = "MANUAL"
    PROCEDURE = "PROCEDURE"
    FORM = "FORM"
    CHECKLIST = "CHECKLIST"
    POLICY = "POLICY"
    OTHER = "OTHER"


class QMSDocStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    OBSOLETE = "OBSOLETE"


class QMSDistributionFormat(str, enum.Enum):
    HARD_COPY = "HARD_COPY"
    SOFT_COPY = "SOFT_COPY"
    CONTROLLED_SOFT_COPY = "CONTROLLED_SOFT_COPY"


class QMSChangeRequestStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    IMPLEMENTED = "IMPLEMENTED"
    CLOSED = "CLOSED"


class QMSAuditKind(str, enum.Enum):
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"
    THIRD_PARTY = "THIRD_PARTY"


class QMSAuditStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    CAP_OPEN = "CAP_OPEN"
    CLOSED = "CLOSED"


class QMSFindingType(str, enum.Enum):
    NON_CONFORMITY = "NON_CONFORMITY"
    OBSERVATION = "OBSERVATION"
    IMPROVEMENT_OPPORTUNITY = "IMPROVEMENT_OPPORTUNITY"


class QMSFindingSeverity(str, enum.Enum):
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"


class FindingLevel(str, enum.Enum):
    LEVEL_1 = "LEVEL_1"
    LEVEL_2 = "LEVEL_2"
    LEVEL_3 = "LEVEL_3"


FINDING_LEVEL_DUE_DAYS: dict[FindingLevel, int] = {
    FindingLevel.LEVEL_1: 7,
    FindingLevel.LEVEL_2: 28,
    FindingLevel.LEVEL_3: 90,
}


def infer_level_from_severity(sev: QMSFindingSeverity) -> FindingLevel:
    # Safe default mapping to meet your Level 1/2/3 rule.
    if sev == QMSFindingSeverity.CRITICAL:
        return FindingLevel.LEVEL_1
    if sev == QMSFindingSeverity.MAJOR:
        return FindingLevel.LEVEL_2
    return FindingLevel.LEVEL_3


class QMSCAPStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"
