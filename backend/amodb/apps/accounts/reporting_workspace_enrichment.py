"""Enrich reporting workspace occupants with mutable assignment state.

The original workspace contract predates assignment correction and transfer
workflows.  Keeping the enrichment in one wrapper avoids duplicating the complex
scope and hierarchy assembly while exposing the exact FTE and matrix-reporting
state required by the lifecycle editor.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from . import corporate_structure_models as org_models

_INSTALLED_FLAG = "_assignment_state_enrichment_installed"


def install_reporting_workspace_enrichment(reporting_module) -> None:
    if getattr(reporting_module, _INSTALLED_FLAG, False):
        return

    original_workspace = reporting_module._workspace

    def enriched_workspace(db: Session, actor):
        workspace = original_workspace(db, actor)
        assignment_ids = {
            occupant.assignment_id
            for position in workspace.positions
            for occupant in position.occupants
        }
        if not assignment_ids:
            return workspace

        rows = (
            db.query(org_models.PositionAssignment)
            .filter(org_models.PositionAssignment.id.in_(list(assignment_ids)))
            .all()
        )
        assignments = {str(row.id): row for row in rows}
        for position in workspace.positions:
            for occupant in position.occupants:
                assignment = assignments.get(occupant.assignment_id)
                if not assignment:
                    continue
                occupant.fte_percent = Decimal(str(assignment.fte_percent or 100))
                occupant.matrix_reporting = bool(assignment.matrix_reporting)
                occupant.matrix_reason = assignment.matrix_reason
        return workspace

    reporting_module._workspace = enriched_workspace
    setattr(reporting_module, _INSTALLED_FLAG, True)
