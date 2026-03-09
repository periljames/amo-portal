from amodb.apps.accounts.models import AMO
from amodb.apps.manuals import models
from amodb.apps.manuals.router import _tenant_by_slug, router


def test_tenant_by_slug_reuses_existing_tenant_for_same_amo(db_session):
    amo = AMO(amo_code="AMO1", name="Demo Name", login_slug="safarilink")
    db_session.add(amo)
    db_session.flush()

    existing = models.Tenant(amo_id=amo.id, slug="old-slug", name="Old Name", settings_json={"ack_due_days": 10})
    db_session.add(existing)
    db_session.commit()

    resolved = _tenant_by_slug(db_session, "safarilink")

    assert resolved.id == existing.id
    assert resolved.slug == "safarilink"
    assert resolved.name == "Demo Name"


def test_master_list_route_precedes_dynamic_manual_route():
    route_paths = [route.path for route in router.routes if hasattr(route, "path")]
    assert route_paths.index("/manuals/t/{tenant_slug}/master-list") < route_paths.index("/manuals/t/{tenant_slug}/{manual_id}")
