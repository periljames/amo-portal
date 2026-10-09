import pytest
from starlette.routing import Match
from amodb.apps.quality.canonical_router import router


@pytest.mark.parametrize(('suffix', 'endpoint'), [
    ('preparation-readiness', 'get_audit_preparation_readiness'),
    ('preparation-context', 'get_audit_preparation_context'),
    ('activity', 'get_audit_activity'),
])
def test_preparation_get_is_dispatched_to_its_authoritative_handler(suffix, endpoint):
    path = f'/api/maintenance/safarilink/quality/audits/f231f732-d27b-4bbd-8b47-a2816ef931d5/{suffix}'
    scope = {'type': 'http', 'path': path, 'method': 'GET', 'root_path': ''}
    match = next(route for route in router.routes if route.matches(scope)[0] == Match.FULL)
    assert match.endpoint.__name__ == endpoint
