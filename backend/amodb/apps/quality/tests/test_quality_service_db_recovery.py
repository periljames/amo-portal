from sqlalchemy.exc import InternalError

from amodb.apps.quality import service as quality_service


class _StubSession:
    def __init__(self):
        self.rolled_back = False

    def in_transaction(self):
        return True

    def rollback(self):
        self.rolled_back = True


class _FailingCountQuery:
    def __init__(self, session):
        self.session = session

    def count(self):
        raise InternalError("SELECT 1", {}, Exception("boom"))


def test_safe_count_rolls_back_session_after_error():
    session = _StubSession()
    query = _FailingCountQuery(session)

    count = quality_service._safe_count(query)

    assert count == 0
    assert session.rolled_back is True
