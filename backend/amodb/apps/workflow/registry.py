from __future__ import annotations

from .guards import (
    guard_audit_close,
    guard_cap_close,
    guard_document_publish,
    guard_finding_close,
    guard_training_participant_completion,
)

WORKFLOWS = {
    "qms_document": {
        "transitions": {
            "DRAFT": {
                "ACTIVE": [guard_document_publish],
            },
            "ACTIVE": {
                "OBSOLETE": [],
            },
        }
    },
    "qms_audit": {
        "transitions": {
            "PLANNED": {
                "IN_PROGRESS": [],
                "CAP_OPEN": [],
                "CLOSED": [guard_audit_close],
            },
            "IN_PROGRESS": {
                "CAP_OPEN": [],
                "CLOSED": [guard_audit_close],
            },
            "CAP_OPEN": {
                "CLOSED": [guard_audit_close],
            },
            "CLOSED": {},
        }
    },
    "qms_finding": {
        "transitions": {
            "OPEN": {"CLOSED": [guard_finding_close]},
            "CLOSED": {},
        }
    },
    "qms_cap": {
        "transitions": {
            "OPEN": {
                "IN_PROGRESS": [],
                "CLOSED": [guard_cap_close],
                "REJECTED": [],
            },
            "IN_PROGRESS": {
                "CLOSED": [guard_cap_close],
                "REJECTED": [],
            },
            "CLOSED": {},
            "REJECTED": {},
        }
    },
    "fracas_case": {
        "transitions": {
            "OPEN": {
                "OPEN": [],
                "IN_ANALYSIS": [],
                "ACTIONS": [],
                "MONITORING": [],
                "CLOSED": [],
            },
            "IN_ANALYSIS": {
                "IN_ANALYSIS": [],
                "ACTIONS": [],
                "MONITORING": [],
                "CLOSED": [],
            },
            "ACTIONS": {
                "ACTIONS": [],
                "MONITORING": [],
                "CLOSED": [],
            },
            "MONITORING": {
                "MONITORING": [],
                "CLOSED": [],
            },
            "CLOSED": {
                "CLOSED": [],
            },
        }
    },
    "training_event": {
        "transitions": {
            "PLANNED": {"IN_PROGRESS": [], "COMPLETED": [], "CANCELLED": []},
            "IN_PROGRESS": {"COMPLETED": [], "CANCELLED": []},
            "COMPLETED": {},
            "CANCELLED": {},
        }
    },
    "training_event_participant": {
        "transitions": {
            "SCHEDULED": {
                "INVITED": [],
                "CONFIRMED": [],
                "ATTENDED": [guard_training_participant_completion],
                "NO_SHOW": [guard_training_participant_completion],
                "CANCELLED": [],
                "DEFERRED": [],
            },
            "INVITED": {
                "CONFIRMED": [],
                "ATTENDED": [guard_training_participant_completion],
                "NO_SHOW": [guard_training_participant_completion],
                "CANCELLED": [],
                "DEFERRED": [],
            },
            "CONFIRMED": {
                "ATTENDED": [guard_training_participant_completion],
                "NO_SHOW": [guard_training_participant_completion],
                "CANCELLED": [],
                "DEFERRED": [],
            },
            "ATTENDED": {},
            "NO_SHOW": {},
            "CANCELLED": {},
            "DEFERRED": {},
        }
    },
}
