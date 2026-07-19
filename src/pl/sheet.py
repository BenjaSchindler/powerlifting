"""Google-Sheet-shaped gym log: build the block sheet, parse it back.

Primary format is CSV: the Drive connector converts an uploaded CSV into a
native Google Sheet (binary xlsx uploads are rejected by the connector), and
exports the filled Sheet back as CSV. All weeks live in ONE tab, stacked as
"SEMANA n" sections — same layout as the athlete's historical coach template
(HEAVY WEIGHT community sheets): Spanish headers, one row per prescribed
slot, one REPS | KG | RPE column triplet per performed set.

Columns:
    Día | Fecha | Ejercicio | Indicaciones | Series | RPE obj | Kg obj |
    S1 Reps | S1 Kg | S1 RPE | ... | Dolor | Notas

Logging rules (also printed at the top of the sheet):
    - Reps done goes in "Sn Reps". Kg left blank means "at target weight".
    - Comma decimals fine (142,5). RPE optional but valued.

An .xlsx builder (one tab per week) is kept for local preview and for a
future connector that accepts binary uploads; both formats parse back.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date as Date
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .models import Block, EntryLog, LoggedSet, PainNote, SessionLog, Target

HEADER_FILL = PatternFill("solid", fgColor="1F2937")
HEADER_FONT = Font(color="FFFFFF", bold=True)
DAY_FILL = PatternFill("solid", fgColor="D1D5DB")
TARGET_FILL = PatternFill("solid", fgColor="F3F4F6")
THIN_TOP = Border(top=Side(style="thin", color="6B7280"))

FIXED_COLS = ["Día", "Fecha", "Ejercicio", "Indicaciones", "Series", "RPE obj", "Kg obj"]
TAIL_COLS = ["Dolor", "Notas"]
N_FIXED = len(FIXED_COLS)
COL_EXERCISE = 3  # 1-indexed
COL_KG_OBJ = N_FIXED

DAY_CELL_RE = re.compile(r"D(?:ía|ia)?\s*(\d+)", re.IGNORECASE)
WEEK_ROW_RE = re.compile(r"SEMANA\s*(\d+)", re.IGNORECASE)

INSTRUCTIONS = [
    "Cómo registrar: reps hechas en 'Sn Reps'; 'Sn Kg' vacío = hiciste el Kg obj;",
    "otro peso va en 'Sn Kg' (coma o punto da igual); RPE por serie si puedes;",
    "Dolor: cualquier molestia (ej 'rodilla izq 3/10'); lo saltado queda en blanco.",
]


def _n_set_cols(block: Block) -> int:
    most = max((s.sets for d in block.days for s in d.slots), default=5)
    return max(4, min(most, 10))


def _week_start(block: Block, week: int) -> Date:
    return block.start_date + timedelta(days=7 * (week - 1))


def headers_for(block: Block) -> list[str]:
    n_sets = _n_set_cols(block)
    set_headers: list[str] = []
    for i in range(1, n_sets + 1):
        set_headers += [f"S{i} Reps", f"S{i} Kg", f"S{i} RPE"]
    return FIXED_COLS + set_headers + TAIL_COLS


def _week_rows(block: Block, week: int, targets_by_week: dict[int, list[Target]]):
    """Yield (first_of_day, row_values) for one week, matching headers_for."""
    n_sets = _n_set_cols(block)
    targets: dict[tuple[int, str], list[Target]] = {}
    for t in targets_by_week.get(week, []):
        targets.setdefault((t.day, t.exercise), []).append(t)
    used: dict[tuple[int, str], int] = {}

    for day in block.days:
        first_of_day = True
        for slot in day.slots:
            key = (day.day, slot.exercise)
            idx = used.get(key, 0)
            used[key] = idx + 1
            tlist = targets.get(key, [])
            t = tlist[idx] if idx < len(tlist) else None

            day_label = f"Día {day.day} — {day.name}" if first_of_day else ""
            date_hint = (
                (_week_start(block, week) + timedelta(days=day.day - 1)).isoformat()
                if first_of_day
                else ""
            )
            rpe_obj = ""
            if slot.intensity and slot.intensity.type == "rpe":
                rpe_obj = f"@{slot.intensity.value:g}"
            elif t and t.percent is not None:
                rpe_obj = f"{t.percent:.0%}"
            kg_obj = f"{t.weight:g}" if t and t.weight is not None else ""

            yield first_of_day, (
                [day_label, date_hint, slot.exercise, slot.notes or "",
                 f"{slot.sets}x{slot.reps}", rpe_obj, kg_obj]
                + [""] * (3 * n_sets)
                + ["", ""]
            )
            first_of_day = False


# --------------------------------------------------------------------------- builders


def build_csv(block: Block, targets_by_week: dict[int, list[Target]]) -> str:
    """One CSV for the whole block: SEMANA sections stacked in one tab."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"{block.name} — {block.id} — inicio {block.start_date.isoformat()}"])
    for line in INSTRUCTIONS:
        w.writerow([line])
    headers = headers_for(block)
    for week in range(1, block.weeks + 1):
        w.writerow([])
        w.writerow([f"SEMANA {week}"])
        w.writerow(headers)
        for _, row in _week_rows(block, week, targets_by_week):
            w.writerow(row)
    return buf.getvalue()


def build_workbook(block: Block, targets_by_week: dict[int, list[Target]], out_path: Path) -> Path:
    """xlsx preview: one tab per week + Info tab."""
    n_sets = _n_set_cols(block)
    headers = headers_for(block)
    wb = Workbook()
    wb.remove(wb.active)

    for week in range(1, block.weeks + 1):
        ws = wb.create_sheet(f"S{week}")
        ws.append(headers)
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=c)
            cell.fill, cell.font = HEADER_FILL, HEADER_FONT
            cell.alignment = Alignment(horizontal="center")
        row = 2
        for first_of_day, values in _week_rows(block, week, targets_by_week):
            ws.append(values)
            ws.cell(row=row, column=COL_KG_OBJ).fill = TARGET_FILL
            if first_of_day:
                for c in range(1, len(headers) + 1):
                    ws.cell(row=row, column=c).border = THIN_TOP
                ws.cell(row=row, column=1).fill = DAY_FILL
                ws.cell(row=row, column=1).font = Font(bold=True)
            row += 1
        widths = {1: 22, 2: 11, 3: 30, 4: 18, 5: 9, 6: 8, 7: 8}
        for i in range(n_sets * 3):
            widths[N_FIXED + 1 + i] = 7
        widths[N_FIXED + 1 + 3 * n_sets] = 14
        widths[N_FIXED + 2 + 3 * n_sets] = 28
        for c, wdt in widths.items():
            ws.column_dimensions[get_column_letter(c)].width = wdt
        ws.freeze_panes = "D2"

    info = wb.create_sheet("Info")
    info.append(["Bloque", block.name])
    info.append(["Id", block.id])
    info.append(["Inicio", block.start_date.isoformat()])
    info.append(["Semanas", block.weeks])
    for line in INSTRUCTIONS:
        info.append([line])
    info.column_dimensions["A"].width = 80
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


# --------------------------------------------------------------------------- parsing


def _cell_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _parse_float(v) -> float | None:
    s = _cell_str(v).replace(",", ".").replace("@", "")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_int(v) -> int | None:
    f = _parse_float(v)
    return int(f) if f is not None else None


def parse_set_triplet(reps_v, kg_v, rpe_v, target_weight: float | None) -> LoggedSet | None:
    """One performed set from its Reps/Kg/RPE cells; blank Kg = target."""
    reps = _parse_int(reps_v)
    if reps is None or reps <= 0:
        return None
    weight = _parse_float(kg_v)
    if weight is None:
        weight = target_weight
    if weight is None:
        return None
    return LoggedSet(weight=weight, reps=reps, rpe=_parse_float(rpe_v))


def _parse_date(v, fallback: Date) -> Date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, Date):
        return v
    s = _cell_str(v)
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return fallback


class _WeekParser:
    """Accumulates sessions for one week from row streams."""

    def __init__(self, block: Block, week: int):
        self.block = block
        self.week = week
        self.n_sets = _n_set_cols(block)
        self.sessions: dict[int, SessionLog] = {}
        self.day_date: dict[int, Date] = {}
        self.current_day = 0

    def feed(self, row: tuple | list) -> None:
        row = list(row) + [None] * (N_FIXED + 3 * self.n_sets + 2 - len(row))
        m = DAY_CELL_RE.search(_cell_str(row[0]))
        if m:
            self.current_day = int(m.group(1))
        if self.current_day == 0:
            return
        fallback = _week_start(self.block, self.week) + timedelta(days=self.current_day - 1)
        if row[1] not in (None, ""):
            self.day_date[self.current_day] = _parse_date(row[1], fallback)
        exercise = _cell_str(row[COL_EXERCISE - 1])
        if not exercise or exercise == "Ejercicio":
            return
        target_w = _parse_float(row[COL_KG_OBJ - 1])
        sets = []
        for i in range(self.n_sets):
            base = N_FIXED + i * 3
            st = parse_set_triplet(row[base], row[base + 1], row[base + 2], target_w)
            if st:
                sets.append(st)
        pain_s = _cell_str(row[N_FIXED + 3 * self.n_sets])
        notes_s = _cell_str(row[N_FIXED + 3 * self.n_sets + 1])
        if not sets and not pain_s and not notes_s:
            return

        sess = self.sessions.setdefault(
            self.current_day,
            SessionLog(
                date=self.day_date.get(self.current_day, fallback),
                block=self.block.id,
                week=self.week,
                day=self.current_day,
            ),
        )
        entry = EntryLog(exercise=exercise, sets=sets)
        rpes = [s.rpe for s in sets if s.rpe is not None]
        if rpes:
            entry.rpe = max(rpes)
        if pain_s:
            entry.pain = PainNote(location=pain_s)
        if notes_s:
            entry.notes = notes_s
        sess.entries.append(entry)

    def result(self) -> list[SessionLog]:
        return [self.sessions[d] for d in sorted(self.sessions)]


def parse_csv_text(
    text: str, block: Block, weeks: list[int] | None = None
) -> dict[int, list[SessionLog]]:
    """Parse the block CSV (or the Sheet's CSV export) back into sessions."""
    parsers: dict[int, _WeekParser] = {}
    current: _WeekParser | None = None
    for row in csv.reader(io.StringIO(text)):
        if not row or all(c.strip() == "" for c in row):
            continue
        m = WEEK_ROW_RE.search(row[0])
        if m:
            week = int(m.group(1))
            if week <= block.weeks:
                current = parsers.setdefault(week, _WeekParser(block, week))
            else:
                current = None
            continue
        if current is not None:
            current.feed(row)
    out = {
        w: p.result()
        for w, p in sorted(parsers.items())
        if p.result() and (not weeks or w in weeks)
    }
    return out


def parse_workbook(
    path: Path, block: Block, weeks: list[int] | None = None
) -> dict[int, list[SessionLog]]:
    """Parse a filled .xlsx (tabs S1..Sn) back into sessions, keyed by week."""
    wb = load_workbook(path, data_only=True)
    out: dict[int, list[SessionLog]] = {}
    for week in range(1, block.weeks + 1):
        if weeks and week not in weeks:
            continue
        name = f"S{week}"
        if name not in wb.sheetnames:
            continue
        parser = _WeekParser(block, week)
        for row in wb[name].iter_rows(min_row=2, values_only=True):
            if row is not None:
                parser.feed(row)
        if parser.result():
            out[week] = parser.result()
    return out


def parse_any(path: Path, block: Block, weeks: list[int] | None = None):
    if path.suffix.lower() == ".csv":
        return parse_csv_text(path.read_text(encoding="utf-8-sig"), block, weeks)
    return parse_workbook(path, block, weeks)
