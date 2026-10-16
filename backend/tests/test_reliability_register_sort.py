"""Tenant-safe SQL sorting regression tests for paginated Reliability workspaces."""
import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base

from amodb.apps.reliability.services import _reliability_order


Base = declarative_base()


class Sample(Base):
    __tablename__ = "test_rel_sort_samples"
    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), nullable=False)
    aircraft = Column(String(36), nullable=False)
    status = Column(String(12), nullable=False)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            Sample(id=1, amo_id="tenant-a", aircraft="5Y-SLA", status="OPEN"),
            Sample(id=2, amo_id="tenant-a", aircraft="5Y-SLC", status="OPEN"),
            Sample(id=3, amo_id="tenant-a", aircraft="5Y-SLB", status="CLOSED"),
            Sample(id=4, amo_id="tenant-b", aircraft="5Y-SLD", status="OPEN"),
            Sample(id=5, amo_id="tenant-a", aircraft="5Y-SLB", status="OPEN"),
        ])
        db.commit()
        yield db
    engine.dispose()


@pytest.mark.parametrize(
    ("column", "direction", "expected"),
    [
        ("aircraft", "asc", [1, 3, 5, 2]),
        ("aircraft", "desc", [2, 5, 3, 1]),
        ("status", "asc", [3, 1, 2, 5]),
        ("status", "desc", [5, 2, 1, 3]),
    ],
)
def test_global_sort_pages_remain_deterministic_and_tenant_scoped(session, column, direction, expected):
    # Reconstruct the 2-row server pages and compare with the complete SQL result.
    def ordered_query():
        return _reliability_order(
            session.query(Sample).filter(Sample.amo_id == "tenant-a"),
            Sample,
            column,
            direction,
            {"aircraft": Sample.aircraft, "status": Sample.status},
        )

    ids = [
        item.id for offset in (0, 2)
        for item in ordered_query().offset(offset).limit(2).all()
    ]
    assert ids == expected
    assert 4 not in ids


@pytest.mark.parametrize(
    ("column", "direction"),
    [
        ("id; DROP TABLE users", "desc"),
        ("__dict__", "desc"),
        ("aircraft", "desc; DELETE"),
    ],
)
def test_sql_sort_allowlist_rejects_untrusted_input(session, column, direction):
    with pytest.raises(ValueError, match="Unsupported reliability sort"):
        _reliability_order(session.query(Sample), Sample, column, direction, {
            "aircraft": Sample.aircraft
        })


def test_id_sort_has_no_extra_order_clause(session):
    query = _reliability_order(session.query(Sample).filter(Sample.amo_id == "tenant-a"),
                               Sample, "id", "desc", {"id": Sample.id})
    assert [row.id for row in query.limit(2).all()] == [5, 3]
