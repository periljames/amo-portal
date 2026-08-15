from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from amodb.apps.rostering import models as roster_models
from amodb.apps.workforce import models, schemas, services
from amodb.database import Base


def _id() -> str:
    return str(uuid4())


def _day(
    index: int,
    shift_id: str | None,
    status: models.PatternDayStatus,
) -> schemas.WorkPatternDayInput:
    return schemas.WorkPatternDayInput(
        cycle_day_index=index,
        shift_template_id=shift_id,
        status=status,
        start_time_local="08:00" if shift_id else None,
        end_time_local="17:00" if shift_id else None,
        planned_minutes=480 if shift_id else 0,
    )


def test_existing_pattern_days_can_be_replaced_repeatedly(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            roster_models.ShiftTemplate.__table__,
            models.WorkPattern.__table__,
            models.WorkPatternDay.__table__,
        ],
    )
    amo_id = _id()
    actor_id = _id()

    with Session(bind=engine, autoflush=False, expire_on_commit=False) as db:
        day_shift = roster_models.ShiftTemplate(
            id=_id(),
            amo_id=amo_id,
            code="DAY",
            label="Day shift",
            kind=roster_models.ShiftTemplateKind.DAY,
            default_start_time="08:00",
            default_end_time="17:00",
            duration_minutes=480,
            counts_as_duty=True,
            is_active=True,
        )
        pattern = models.WorkPattern(
            id=_id(),
            amo_id=amo_id,
            code="5-2",
            name="Five on, two off",
            cycle_length_days=7,
            timezone_name="UTC",
            created_by_user_id=actor_id,
            updated_by_user_id=actor_id,
        )
        pattern.days = [
            models.WorkPatternDay(
                amo_id=amo_id,
                cycle_day_index=index,
                shift_template_id=day_shift.id if index < 5 else None,
                status=models.PatternDayStatus.DUTY if index < 5 else models.PatternDayStatus.OFF,
                start_time_local="08:00" if index < 5 else None,
                end_time_local="17:00" if index < 5 else None,
                planned_minutes=480 if index < 5 else 0,
            )
            for index in range(7)
        ]
        db.add_all([day_shift, pattern])
        db.commit()
        original_day_ids = {day.id for day in pattern.days}

        monkeypatch.setattr(services, "_audit", lambda *args, **kwargs: None)
        services.update_pattern(
            db,
            row=pattern,
            actor_user_id=actor_id,
            payload=schemas.WorkPatternUpdate(
                name="Four on, four off",
                cycle_length_days=8,
                days=[
                    _day(
                        index,
                        day_shift.id if index < 4 else None,
                        models.PatternDayStatus.DUTY
                        if index < 4
                        else models.PatternDayStatus.OFF,
                    )
                    for index in range(8)
                ],
            ),
        )
        db.commit()

        assert pattern.name == "Four on, four off"
        assert len(pattern.days) == 8
        assert {day.id for day in pattern.days}.isdisjoint(original_day_ids)
        assert db.query(models.WorkPatternDay).filter_by(work_pattern_id=pattern.id).count() == 8

        services.update_pattern(
            db,
            row=pattern,
            actor_user_id=actor_id,
            payload=schemas.WorkPatternUpdate(
                description="Second successful edit",
                days=[
                    _day(
                        index,
                        day_shift.id if index % 2 == 0 else None,
                        models.PatternDayStatus.DUTY
                        if index % 2 == 0
                        else models.PatternDayStatus.OFF,
                    )
                    for index in range(8)
                ],
            ),
        )
        db.commit()

        assert pattern.description == "Second successful edit"
        assert [day.cycle_day_index for day in pattern.days] == list(range(8))
        assert db.query(models.WorkPatternDay).filter_by(work_pattern_id=pattern.id).count() == 8

    engine.dispose()


def test_pattern_update_rejects_duplicate_cycle_days_before_persistence() -> None:
    with pytest.raises(ValidationError, match="cycle_day_index values must be unique"):
        schemas.WorkPatternUpdate(
            cycle_length_days=2,
            days=[
                _day(0, None, models.PatternDayStatus.OFF),
                _day(0, None, models.PatternDayStatus.OFF),
            ],
        )
