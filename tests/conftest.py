from datetime import date

import pytest

from pl.models import (
    Athlete,
    Block,
    DaySpec,
    EntryLog,
    Exercise,
    LoggedSet,
    MaxEntry,
    PainEvent,
    Scheme,
    SessionLog,
    Slot,
)


@pytest.fixture
def catalog() -> dict[str, Exercise]:
    exs = [
        Exercise(
            id="squat", name="Back Squat", category="main", pattern="squat",
            muscles=["quads", "glutes"], joints=["knee", "hip", "lumbar"],
        ),
        Exercise(
            id="bench", name="Bench Press", category="main", pattern="press",
            muscles=["pecs", "triceps"], joints=["shoulder", "elbow"],
        ),
        Exercise(
            id="deadlift", name="Deadlift", category="main", pattern="hinge",
            muscles=["hamstrings", "glutes", "spinal_erectors"], joints=["hip", "lumbar"],
        ),
        Exercise(
            id="pause-squat", name="Pause Squat", category="variation", parent="squat",
            pattern="squat", muscles=["quads", "glutes"], joints=["knee", "hip", "lumbar"],
        ),
        Exercise(
            id="db-row", name="Dumbbell Row", category="accessory", pattern="pull",
            muscles=["lats"], joints=["shoulder", "elbow"],
        ),
    ]
    return {e.id: e for e in exs}


@pytest.fixture
def athlete() -> Athlete:
    return Athlete(
        name="Test",
        plate_increment=2.5,
        current_maxes={"deadlift": MaxEntry(weight=200.0, source="estimated")},
    )


@pytest.fixture
def block() -> Block:
    return Block(
        id="2026-07-test",
        name="Test Block",
        start_date=date(2026, 7, 6),
        weeks=3,
        status="active",
        schemes=[
            Scheme(id="wave", kind="percent_wave", week_percents=[0.75, 0.80, 0.60]),
            Scheme(id="dp", kind="double_progression", rep_quality_rpe=8.0, increment_pct=0.025),
        ],
        default_scheme="wave",
        days=[
            DaySpec(
                day=1,
                name="Squat + Bench",
                slots=[
                    Slot(exercise="squat", sets=5, reps="5"),
                    Slot(exercise="bench", sets=4, reps="6"),
                    Slot(exercise="db-row", sets=3, reps="8-12", scheme="dp"),
                ],
            ),
            DaySpec(
                day=2,
                name="Deadlift",
                slots=[
                    Slot(exercise="deadlift", sets=3, reps="5"),
                    Slot(exercise="pause-squat", sets=3, reps="3"),
                ],
            ),
        ],
    )


@pytest.fixture
def history(block) -> list[SessionLog]:
    return [
        SessionLog(
            date=date(2026, 7, 7),
            block=block.id,
            week=1,
            day=1,
            entries=[
                EntryLog(
                    exercise="squat",
                    sets=[LoggedSet(weight=140, reps=5, rpe=8)] * 5,
                ),
                EntryLog(
                    exercise="bench",
                    sets=[LoggedSet(weight=100, reps=6)] * 4,
                    rpe=8.5,
                ),
                EntryLog(
                    exercise="db-row",
                    sets=[LoggedSet(weight=30, reps=12, rpe=7)] * 3,
                ),
            ],
        )
    ]


@pytest.fixture
def pain_log() -> list[PainEvent]:
    return [
        PainEvent(
            date=date(2026, 7, 8),
            location="left_knee",
            severity=4,
            exercise="squat",
            context="last set of 5x5",
        )
    ]
