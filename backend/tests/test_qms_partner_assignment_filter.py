"""Partner audit deep links must not broaden their original assignment grant."""
from __future__ import annotations

import inspect

from amodb.apps.procurement import external_partner_router


def test_quality_projection_rechecks_audit_filter_against_member_grant():
    source = inspect.getsource(external_partner_router.quality)
    assert 'audit_id not in {str(value) for value in assignments}' in source
    assert 'raise HTTPException(404,"Assigned Quality audit not found")' in source
    assert source.count(":focus") >= 5
    assert 'CAST(n.audit_id AS TEXT) IN :assigned' in source
    assert 'CAST(f.audit_id AS TEXT) IN :assigned' in source
    assert "AND related_id IN :assigned" in source
