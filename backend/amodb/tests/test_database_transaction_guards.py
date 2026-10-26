from types import SimpleNamespace
from unittest.mock import Mock

from amodb import database


def connection(dialect="postgresql"):
    return SimpleNamespace(dialect=SimpleNamespace(name=dialect), exec_driver_sql=Mock())


def test_timeout_guards_remain_transaction_local_in_one_round_trip():
    c = connection()
    database._apply_transaction_guards(object(), None, c)
    sql = c.exec_driver_sql.call_args.args[0]
    assert c.exec_driver_sql.call_count == 1
    assert "set_config('statement_timeout'" in sql
    assert "set_config('idle_in_transaction_session_timeout'" in sql
    assert sql.count(", true)") == 2


def test_read_only_transactions_keep_the_write_protection(monkeypatch):
    monkeypatch.setattr(database, "READ_ONLY_TRANSACTIONS", True)
    c = connection()
    database._apply_transaction_guards(database.ReadOnlySession(), None, c)
    assert c.exec_driver_sql.call_args.args[0] == "SET TRANSACTION READ ONLY"
    assert c.exec_driver_sql.call_count == 2


def test_sqlite_does_not_receive_postgres_guards():
    c = connection("sqlite")
    database._apply_transaction_guards(object(), None, c)
    c.exec_driver_sql.assert_not_called()
