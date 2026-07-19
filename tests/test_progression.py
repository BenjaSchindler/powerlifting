from datetime import date

from pl.models import EntryLog, LoggedSet, SessionLog
from pl.progression import round_to_increment, suggest_block, suggest_week

TODAY = date(2026, 7, 20)


def test_round_to_increment():
    assert round_to_increment(141.3, 2.5) == 142.5
    assert round_to_increment(139.9, 2.5) == 140.0


def test_percent_wave_uses_e1rm(block, history, athlete, catalog):
    targets = suggest_week(block, 2, history, athlete, catalog, [], today=TODAY)
    squat = next(t for t in targets if t.exercise == "squat")
    # e1RM of 140x5@8 = 172.7 -> 80% = 138.1 -> rounds to 137.5
    assert squat.percent == 0.80
    assert squat.weight == 137.5
    assert "e1RM" in squat.rationale


def test_percent_wave_without_base_warns(block, athlete, catalog):
    targets = suggest_week(block, 1, [], athlete, catalog, [], today=TODAY)
    bench = next(t for t in targets if t.exercise == "bench")
    assert bench.weight is None
    assert any("set weight manually" in w for w in bench.warnings)


def test_double_progression_bumps_after_clean_top_sets(block, history, athlete, catalog):
    targets = suggest_week(block, 2, history, athlete, catalog, [], today=TODAY)
    row = next(t for t in targets if t.exercise == "db-row")
    # 30kg 3x12 @ rpe7: all sets at top of 8-12 cleanly -> bump ~2.5%, min one increment
    assert row.weight == 32.5
    assert "move up" in row.rationale


def test_double_progression_holds_when_reps_short(block, history, athlete, catalog):
    history[0].entries[2].sets = [LoggedSet(weight=30, reps=9, rpe=8)] * 3
    targets = suggest_week(block, 2, history, athlete, catalog, [], today=TODAY)
    row = next(t for t in targets if t.exercise == "db-row")
    assert row.weight == 30
    assert "add reps" in row.rationale


def test_pain_guardrail_warns_on_matching_joints(block, history, athlete, catalog, pain_log):
    targets = suggest_week(block, 2, history, athlete, catalog, pain_log, today=TODAY)
    squat = next(t for t in targets if t.exercise == "squat")
    bench = next(t for t in targets if t.exercise == "bench")
    assert any("left_knee" in w for w in squat.warnings)
    assert not bench.warnings
    pause = next(t for t in targets if t.exercise == "pause-squat")
    assert any("left_knee" in w for w in pause.warnings)


def test_suggest_block_blanks_dp_after_week1(block, history, athlete, catalog):
    by_week = suggest_block(block, history, athlete, catalog, [], today=TODAY)
    assert len(by_week) == block.weeks
    w1_row = next(t for t in by_week[1] if t.exercise == "db-row")
    w2_row = next(t for t in by_week[2] if t.exercise == "db-row")
    assert w1_row.weight is not None
    assert w2_row.weight is None
    assert "after logging" in w2_row.rationale


def test_deload_week_uses_third_percent(block, history, athlete, catalog):
    targets = suggest_week(block, 3, history, athlete, catalog, [], today=TODAY)
    squat = next(t for t in targets if t.exercise == "squat")
    assert squat.percent == 0.60


def test_rpe_wave_derives_kg_from_chart(block, history, athlete, catalog):
    from pl.analytics import epley_e1rm, rpe_percent
    from pl.models import Scheme

    block.schemes.append(Scheme(id="rw", kind="rpe_wave", week_rpes=[6, 7, 5]))
    block.days[0].slots[0].scheme = "rw"  # squat 5x5 now rpe-driven
    targets = suggest_week(block, 2, history, athlete, catalog, [], today=TODAY)
    squat = next(t for t in targets if t.exercise == "squat")
    e1 = epley_e1rm(140, 5, 8)
    expected_pct = rpe_percent(5, 7)
    assert squat.percent == round(expected_pct, 4)
    assert abs(squat.weight - round(e1 * expected_pct / 2.5) * 2.5) < 0.01
    assert "@RPE 7" in squat.rationale


def test_fixed_rpe_intensity_without_scheme(block, history, athlete, catalog):
    from pl.models import Intensity, Slot

    block.days[0].slots.append(
        Slot(exercise="squat", sets=1, reps="3", intensity=Intensity(type="rpe", value=8), scheme="none")
    )
    targets = suggest_week(block, 1, history, athlete, catalog, [], today=TODAY)
    single = next(t for t in targets if t.exercise == "squat" and t.reps == "3")
    assert single.weight is not None
    assert "@RPE 8" in single.rationale
