import csv
import io
from datetime import date

from openpyxl import load_workbook

from pl.progression import suggest_block
from pl.sheet import (
    build_csv,
    build_workbook,
    parse_csv_text,
    parse_set_triplet,
    parse_workbook,
)

TODAY = date(2026, 7, 20)

# test block: n_sets = max sets (5); 7 fixed cols -> triplets at cols 8..22,
# Dolor 23, Notas 24
C_REPS = lambda i: 8 + 3 * i
C_KG = lambda i: 9 + 3 * i
C_RPE = lambda i: 10 + 3 * i
C_DOLOR = 23


def test_parse_set_triplet_variants():
    st = parse_set_triplet("5", None, None, 140)
    assert st.weight == 140 and st.reps == 5 and st.rpe is None
    st = parse_set_triplet(5, "142,5", 8, 140)
    assert st.weight == 142.5 and st.rpe == 8
    st = parse_set_triplet("3", None, "8,5", None)
    assert st is None  # no kg anywhere
    assert parse_set_triplet("", "140", "8", 140) is None  # no reps = not done
    assert parse_set_triplet(None, None, None, 140) is None


def test_roundtrip_build_fill_parse(tmp_path, block, history, athlete, catalog):
    targets = suggest_block(block, history, athlete, catalog, [], today=TODAY)
    path = build_workbook(block, targets, tmp_path / "block.xlsx", catalog)

    wb = load_workbook(path)
    assert set(wb.sheetnames) == {"S1", "S2", "S3", "Info"}

    # fill week 2 like a gym session: squat done at target, bench at own
    # weight, deadlift date-only (no sets), pain noted on squat.
    # The sheet shows catalog display names; parsing resolves them to ids.
    ws = wb["S2"]
    rows = {r[0].row: [c.value for c in r] for r in ws.iter_rows(min_row=2)}
    squat_row = next(r for r, v in rows.items() if v[2] == "Back Squat")
    bench_row = next(r for r, v in rows.items() if v[2] == "Bench Press")
    dead_row = next(r for r, v in rows.items() if v[2] == "Deadlift")

    for i in range(5):
        ws.cell(row=squat_row, column=C_REPS(i), value="5")
        ws.cell(row=squat_row, column=C_RPE(i), value="8" if i < 4 else "8,5")
    ws.cell(row=squat_row, column=C_DOLOR, value="rodilla izq 2/10")
    for i in range(4):
        ws.cell(row=bench_row, column=C_REPS(i), value=6)
        ws.cell(row=bench_row, column=C_KG(i), value="102,5")
    ws.cell(row=dead_row, column=2, value="2026-07-15")
    filled = tmp_path / "filled.xlsx"
    wb.save(filled)

    parsed = parse_workbook(filled, block, catalog=catalog)
    assert list(parsed.keys()) == [2]
    (sess,) = parsed[2]
    assert sess.week == 2 and sess.day == 1 and sess.block == block.id
    by_ex = {e.exercise: e for e in sess.entries}
    assert set(by_ex) == {"squat", "bench"}

    squat = by_ex["squat"]
    assert len(squat.sets) == 5
    assert squat.sets[0].weight == 137.5  # Kg obj cell (80% wave of e1RM 172.7)
    assert squat.sets[0].rpe == 8
    assert squat.rpe == 8.5  # max of per-set RPEs
    assert squat.pain and squat.pain.location == "rodilla izq 2/10"

    bench = by_ex["bench"]
    assert all(s.weight == 102.5 and s.reps == 6 for s in bench.sets)


def test_parse_empty_workbook_yields_nothing(tmp_path, block, history, athlete, catalog):
    targets = suggest_block(block, history, athlete, catalog, [], today=TODAY)
    path = build_workbook(block, targets, tmp_path / "empty.xlsx", catalog)
    assert parse_workbook(path, block, catalog=catalog) == {}


def test_duplicate_exercise_rows_same_day(tmp_path, block, history, athlete, catalog):
    """Top single + backoffs style: same exercise twice in one day."""
    from pl.models import Intensity, Slot

    block.days[0].slots.insert(
        0, Slot(exercise="squat", sets=1, reps="3", intensity=Intensity(type="rpe", value=8))
    )
    targets = suggest_block(block, history, athlete, catalog, [], today=TODAY)
    path = build_workbook(block, targets, tmp_path / "dup.xlsx")
    ws = load_workbook(path)["S1"]
    squat_rows = [r for r in ws.iter_rows(min_row=2) if r[2].value == "squat"]
    assert len(squat_rows) == 2
    assert squat_rows[0][4].value == "1x3"  # top single row first
    assert squat_rows[0][5].value == "@8"
    assert squat_rows[1][4].value == "5x5"


def test_csv_roundtrip_like_google_sheet(block, history, athlete, catalog):
    """Build CSV -> 'fill it in Google Sheets' -> export CSV -> parse."""
    targets = suggest_block(block, history, athlete, catalog, [], today=TODAY)
    text = build_csv(block, targets, catalog)
    rows = list(csv.reader(io.StringIO(text)))
    assert any(r and r[0] == "SEMANA 2" for r in rows)

    # simulate gym logging in week 2: squat at target with comma-decimal kg
    # override on last set, pain note; everything else untouched
    filled = []
    in_w2 = False
    for r in rows:
        label = r[0] if r else ""
        if label.startswith("SEMANA"):
            in_w2 = label == "SEMANA 2"
        if in_w2 and len(r) > 3 and r[2] == "Back Squat":
            r = r[:]
            for i in range(5):
                r[7 + 3 * i] = "5"
            r[8 + 3 * 4] = "135,0"  # S5 Kg: lighter last set
            r[9 + 3 * 4] = "9"  # S5 RPE
            r[22] = "rodilla izq 2/10"  # Dolor
        filled.append(r)
    out = io.StringIO()
    csv.writer(out).writerows(filled)

    parsed = parse_csv_text(out.getvalue(), block, catalog=catalog)
    assert list(parsed.keys()) == [2]
    (sess,) = parsed[2]
    squat = next(e for e in sess.entries if e.exercise == "squat")
    assert len(squat.sets) == 5
    assert squat.sets[0].weight == 137.5  # Kg obj
    assert squat.sets[4].weight == 135.0  # comma decimal override
    assert squat.rpe == 9
    assert squat.pain and "rodilla" in squat.pain.location


def test_rpe_wave_slots_print_target_rpe(block, history, athlete, catalog):
    """rpe_wave prescriptions show '@7' in RPE obj (his coach dialect),
    not a raw percent; percent_wave slots keep showing the percent."""
    from pl.models import Scheme

    block.schemes.append(Scheme(id="top", kind="rpe_wave", week_rpes=[7, 8, 6]))
    block.days[0].slots[0].scheme = "top"
    targets = suggest_block(block, history, athlete, catalog, [], today=TODAY)
    text = build_csv(block, targets, catalog)
    week1 = text.split("SEMANA 2")[0]
    squat_line = next(
        line for line in week1.splitlines() if "Back Squat" in line
    )
    assert ",@7," in squat_line
    bench_line = next(line for line in week1.splitlines() if "Bench Press" in line)
    assert ",75%," in bench_line  # percent_wave week 1


def test_prescription_notes_do_not_create_phantom_sessions(
    tmp_path, block, history, athlete, catalog
):
    """Slot cues live in Indicaciones, so an untouched sheet parses empty."""
    block.days[0].slots[0].notes = "PAUSA COMP"
    targets = suggest_block(block, history, athlete, catalog, [], today=TODAY)
    path = build_workbook(block, targets, tmp_path / "cues.xlsx")
    ws = load_workbook(path)["S1"]
    squat_row = next(r for r in ws.iter_rows(min_row=2) if r[2].value == "squat")
    assert squat_row[3].value == "PAUSA COMP"  # Indicaciones col
    assert parse_workbook(path, block) == {}
