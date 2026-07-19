from datetime import date

import pytest

from pl import insights
from pl.models import (
    Block,
    DaySpec,
    EntryLog,
    Intensity,
    LoggedSet,
    Playbook,
    Scheme,
    SessionLog,
    Slot,
)
from pl.progression import suggest_week


@pytest.fixture
def rpe_block() -> Block:
    return Block(
        id="2026-07-rpe",
        name="RPE Test",
        start_date=date(2026, 7, 6),
        weeks=2,
        status="active",
        schemes=[
            Scheme(id="wave", kind="rpe_wave", week_rpes=[7, 8]),
            Scheme(id="dp", kind="double_progression"),
        ],
        default_scheme="wave",
        days=[
            DaySpec(
                day=1,
                name="D1",
                slots=[
                    Slot(exercise="squat", sets=3, reps="5"),
                    Slot(exercise="db-row", sets=3, reps="8-12", scheme="dp"),
                ],
            )
        ],
    )


def _session(d: date, week: int, entries: list[EntryLog]) -> SessionLog:
    return SessionLog(date=d, block="2026-07-rpe", week=week, day=1, entries=entries)


@pytest.fixture
def rpe_logs() -> list[SessionLog]:
    return [
        _session(
            date(2026, 7, 7),
            1,
            [
                EntryLog(exercise="squat", sets=[LoggedSet(weight=140, reps=5, rpe=8)] * 3),
                EntryLog(exercise="db-row", sets=[LoggedSet(weight=30, reps=10, rpe=7)] * 3),
            ],
        ),
        _session(
            date(2026, 7, 14),
            2,
            [EntryLog(exercise="squat", sets=[LoggedSet(weight=150, reps=5, rpe=8)] * 3)],
        ),
    ]


def test_bottom_reps():
    assert insights.bottom_reps("8-12") == 8
    assert insights.bottom_reps("5") == 5
    assert insights.bottom_reps("5+") == 5


def test_target_rpe_slot_cap(rpe_block):
    slot = rpe_block.days[0].slots[0]
    assert insights.target_rpe(rpe_block, slot, 1) == 7
    assert insights.target_rpe(rpe_block, slot, 2) == 8
    capped = Slot(exercise="squat", sets=3, reps="5", intensity=Intensity(type="rpe", value=6))
    assert insights.target_rpe(rpe_block, capped, 2) == 6


def test_rpe_drift_detects_hot_week(rpe_block, rpe_logs):
    drifts = insights.rpe_drift(rpe_block, rpe_logs)
    assert [d["week"] for d in drifts] == [1, 2]
    w1, w2 = drifts
    # db-row has no RPE prescription (double progression) — only squat counts
    assert w1["n"] == 1 and w1["drift"] == pytest.approx(1.0) and w1["hot"]
    assert w2["n"] == 1 and w2["drift"] == pytest.approx(0.0) and not w2["hot"]


def test_red_flags_rpe_and_missed_reps(rpe_block):
    logs = [
        _session(
            date(2026, 7, 14),
            2,
            [EntryLog(exercise="squat", sets=[LoggedSet(weight=160, reps=3, rpe=9.6)])],
        )
    ]
    flags = insights.red_flags(rpe_block, logs)
    kinds = {f["kind"] for f in flags}
    assert kinds == {"rpe", "missed_reps"}


def test_block_response_measures_e1rm_move(rpe_block, rpe_logs):
    resp = {r["exercise"]: r for r in insights.block_response(rpe_block, rpe_logs)}
    squat = resp["squat"]
    assert squat["points"] == 2
    assert squat["e1rm_end"] > squat["e1rm_start"]
    assert squat["delta_pct"] > insights.RESPONSE_THRESHOLD


def test_review_scaffold(rpe_block, rpe_logs, catalog, pain_log):
    rev = insights.build_review_scaffold(rpe_block, rpe_logs, catalog, pain_log)
    assert rev.block == "2026-07-rpe"
    lifts = {lift.exercise: lift for lift in rev.lifts}
    assert "squat" in lifts and lifts["squat"].verdict == "responded"
    assert "db-row" not in lifts  # accessories stay out of the response model
    assert rev.avg_rpe_drift == pytest.approx(0.5)
    assert rev.pain_event_count == 1  # 2026-07-08 falls inside the block window
    assert rev.completed == date(2026, 7, 14)


def test_playbook_warnings(catalog):
    catalog["squat"].playbook = Playbook(swaps=["nope"])
    assert insights.playbook_warnings(catalog) == ["squat: playbook swap 'nope' not in catalog"]
    catalog["squat"].playbook = Playbook(swaps=["pause-squat"])
    assert insights.playbook_warnings(catalog) == []


def test_pain_warning_offers_playbook_swaps(block, history, athlete, catalog, pain_log):
    catalog["squat"].playbook = Playbook(swaps=["pause-squat"])
    targets = suggest_week(block, 1, history, athlete, catalog, pain_log)
    squat = next(t for t in targets if t.exercise == "squat")
    assert any("Pause Squat" in w for w in squat.warnings)
