from datetime import date

from pl.analytics import (
    current_e1rm,
    e1rm_history,
    epley_e1rm,
    find_new_prs,
    open_pain_flags,
    pain_touches,
    rep_prs,
    weekly_tonnage,
)
from pl.models import EntryLog, LoggedSet, PainEvent, SessionLog


def test_epley_plain():
    assert epley_e1rm(100, 1) == 100
    assert round(epley_e1rm(100, 5), 1) == 116.7


def test_epley_rpe_credits_reps_in_reserve():
    # 5 reps @ RPE 8 ~ 7 effective reps
    harder = epley_e1rm(100, 5, rpe=10)
    easier = epley_e1rm(100, 5, rpe=8)
    assert easier > harder
    assert round(easier, 1) == round(100 * (1 + 7 / 30), 1)


def test_current_e1rm_prefers_recent_sets(history, athlete, catalog):
    e1, src = current_e1rm(history, "squat", athlete, today=date(2026, 7, 20))
    assert e1 and round(e1, 1) == round(epley_e1rm(140, 5, 8), 1)
    assert "140" in src


def test_current_e1rm_window_expires(history, athlete, catalog):
    e1, src = current_e1rm(history, "squat", athlete, today=date(2026, 12, 1))
    assert e1 is None and src == "no data"


def test_current_e1rm_falls_back_to_athlete_max(history, athlete, catalog):
    e1, src = current_e1rm(history, "deadlift", athlete, today=date(2026, 7, 20))
    assert e1 == 200.0
    assert "athlete.yaml" in src


def test_current_e1rm_variation_falls_back_to_parent(history, athlete, catalog):
    e1, src = current_e1rm(
        history, "pause-squat", athlete, today=date(2026, 7, 20), catalog=catalog
    )
    assert e1 is not None
    assert "parent" in src


def test_rep_prs_and_new_prs(history):
    prs = rep_prs(history, "squat")
    assert prs[5][0] == 140
    new = SessionLog(
        date=date(2026, 7, 14),
        entries=[EntryLog(exercise="squat", sets=[LoggedSet(weight=145, reps=5)])],
    )
    lines = find_new_prs(history, new)
    assert lines == ["squat: 145 x 5 rep PR (was 140)"]


def test_e1rm_history_one_point_per_day(history):
    hist = e1rm_history(history, "squat")
    assert len(hist) == 1
    assert hist[0][0] == date(2026, 7, 7)


def test_weekly_tonnage_maps_muscles(history, catalog):
    ton = weekly_tonnage(history, catalog)
    wk = f"{date(2026, 7, 7).isocalendar().year}-W{date(2026, 7, 7).isocalendar().week:02d}"
    assert ton[wk]["quads"] == 140 * 5 * 5
    assert ton[wk]["pecs"] == 100 * 6 * 4


def test_pain_flags_and_touch(pain_log, catalog):
    flags = open_pain_flags(pain_log, today=date(2026, 7, 20))
    assert len(flags) == 1
    assert pain_touches(flags[0], catalog["squat"])
    assert not pain_touches(flags[0], catalog["bench"])
    resolved = PainEvent(**{**pain_log[0].model_dump(), "resolved": date(2026, 7, 15)})
    assert open_pain_flags([resolved], today=date(2026, 7, 20)) == []
