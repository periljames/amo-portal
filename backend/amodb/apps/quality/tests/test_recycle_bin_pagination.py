from datetime import datetime, timedelta, timezone, date
from amodb.apps.accounts import models as accounts
from amodb.apps.quality import models, register_pagination


def population(db):
    amo=accounts.AMO(amo_code="BIN",name="Recycle",login_slug="bin")
    other=accounts.AMO(amo_code="OTHERBIN",name="Other",login_slug="otherbin")
    db.add_all([amo,other]);db.flush()
    user=accounts.User(amo_id=amo.id,email="bin@example.com",staff_code="BIN1",first_name="Bin",last_name="Test",full_name="Bin Test",hashed_password="unused",role=accounts.AccountRole.AMO_ADMIN,is_amo_admin=True,is_active=True)
    db.add(user)
    now=datetime.now(timezone.utc)
    for i in range(6):
        db.add(models.QMSAudit(amo_id=amo.id,domain=models.QMSDomain.AMO,kind=models.QMSAuditKind.INTERNAL,audit_ref=f"BIN/{i}",ref_sequence=i+1,title=f"Deleted {i}",deleted_at=now-timedelta(days=i+1)))
    db.add(models.QMSAudit(amo_id=other.id,domain=models.QMSDomain.AMO,kind=models.QMSAuditKind.INTERNAL,audit_ref="FOREIGN",title="Foreign deleted",deleted_at=now))
    db.add(models.QMSAudit(amo_id=amo.id,domain=models.QMSDomain.AMO,kind=models.QMSAuditKind.INTERNAL,audit_ref="LIVE",ref_sequence=99,title="Active audit"))
    db.add(models.QMSAuditSchedule(amo_id=amo.id,domain=models.QMSDomain.AMO,title="Recurring maintenance",next_due_date=date.today(),deleted_at=now-timedelta(days=25)))
    db.commit();return user


def read(db,user,**updates):
    params=dict(domain=models.QMSDomain.AMO,record_type="all",search=None,sort="deletedAt",direction="desc",limit=2,offset=0,db=db,current_user=user)
    params.update(updates)
    return register_pagination.get_recycle_bin_paged(**params)


def test_bin_is_bounded_and_excludes_active_and_other_tenant_records(db_session):
    user=population(db_session)
    result=read(db_session,user)
    assert result["total"]==7
    assert len(result["items"])==2
    assert [item["reference"] for item in result["items"]]==["BIN/0","BIN/1"]
    assert result["summary"]==dict(total=7,audits=6,schedules=1,expiringSoon=1)
    assert all(item["daysRemaining"]>=0 and item["purgeAt"] for item in result["items"])


def test_bin_can_jump_to_later_pages_and_filter_across_the_full_population(db_session):
    user=population(db_session)
    assert [row["reference"] for row in read(db_session,user,offset=4)["items"]]==["BIN/4","BIN/5"]
    result=read(db_session,user,search="Recurring")
    assert result["total"]==1 and result["items"][0]["recordType"]=="schedule"
    assert read(db_session,user,record_type="audit")["total"]==6
    assert read(db_session,user,offset=1000)["items"]==[]


def test_bin_sorting_is_applied_before_pagination(db_session):
    user=population(db_session)
    result=read(db_session,user,record_type="audit",sort="title",direction="desc")
    assert [row["title"] for row in result["items"]]==["Deleted 5","Deleted 4"]


def test_canonical_recycle_page_owns_url():
    from amodb.apps.quality.canonical_router import router
    from starlette.routing import Match
    scope = {"type": "http", "method": "GET", "path": "/api/maintenance/AMO/quality/audits/recycle-bin/paged", "root_path": ""}
    matched = next(route for route in router.routes if route.matches(scope)[0] == Match.FULL)
    assert matched.endpoint is register_pagination.get_recycle_bin_paged
