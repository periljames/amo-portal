import json
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.apps.quality.canonical_core_router import qms_activity_log
from amodb.apps.quality.tests.test_management_review_workflow import client  # noqa: F401


def test_activity_history_returns_changes_and_filters_with_tenant_scope(client):
    client.connection.execute(text("""INSERT INTO qms_activity_logs
        (id,amo_id,actor_user_id,action,module,entity_type,entity_id,previous_value,new_value,created_at)
        VALUES ('event-a','tenant-a','chair','REVIEW_APPROVED','management-review','qms_management_reviews','review-a','{"status":"PENDING_APPROVAL"}','{"status":"APPROVED"}',CURRENT_TIMESTAMP),
               ('event-b','tenant-b','outsider','REVIEW_APPROVED','management-review','qms_management_reviews','review-b','{}','{}',CURRENT_TIMESTAMP)"""))
    client.connection.commit()
    with Session(bind=client.connection) as db:
        result = qms_activity_log(limit=30, offset=0, q="review-a", module="management-review", ctx=client.ctx, db=db)
        assert result["total"] == 1
        event = result["items"][0]
        assert event["action"] == "REVIEW_APPROVED"
        assert event["actor_name"] == "chair@example.test"
        previous = event["previous_value"]
        assert (json.loads(previous) if isinstance(previous, str) else previous)["status"] == "PENDING_APPROVAL"
        after = event["new_value"]
        assert (json.loads(after) if isinstance(after, str) else after)["status"] == "APPROVED"
        assert qms_activity_log(limit=30, offset=30, q="", module="", ctx=client.ctx, db=db)["items"] == []
        assert qms_activity_log(limit=30, offset=0, q="review-b", module="", ctx=client.ctx, db=db)["total"] == 0
