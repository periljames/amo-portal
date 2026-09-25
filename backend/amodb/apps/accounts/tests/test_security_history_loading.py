from sqlalchemy import event

from amodb.apps.accounts.models import User, AccountSecurityEvent


def test_user_lookup_does_not_fetch_security_history_until_requested(db_session):
    user = User(id="history-user", amo_id="history-tenant", staff_code="H1",
                email="history@example.test", first_name="History", last_name="Test",
                full_name="History Test", hashed_password="unused-test-hash")
    db_session.add(user)
    db_session.add(AccountSecurityEvent(user_id=user.id, event_type="LOGIN_SUCCESS"))
    db_session.commit()
    db_session.expunge_all()
    queries = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        loaded = db_session.query(User).filter(User.id == "history-user").one()
        assert not any("account_security_events" in query for query in queries)
        assert len(loaded.security_events) == 1
        assert any("account_security_events" in query for query in queries)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
