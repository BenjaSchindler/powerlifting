"""Pattern mining over the training history.

Deterministic detectors the coach reads at session start: fatigue (RPE
drift vs. plan), red-flag sets, load trends, pain-vs-load context, and how
each block actually moved the lifts. Pure functions — no I/O.
"""

from __future__ import annotations

from datetime import timedelta

from .analytics import e1rm_history, pain_touches, weekly_tonnage
from .models import (
    Block,
    BlockReview,
    EntryLog,
    Exercise,
    LiftReview,
    PainEvent,
    SessionLog,
    Slot,
)

HOT_DRIFT = 0.5  # mean actual-vs-planned RPE gap that counts as running hot
RED_FLAG_RPE = 9.5
RESPONSE_THRESHOLD = 0.015  # e1RM move (fraction) separating responded/flat/regressed


def bottom_reps(reps: str) -> int:
    """Bottom of the rep range: '8-12' -> 8, '5' -> 5, '5+' -> 5."""
    return int(reps.replace("+", "").split("-")[0])


def target_rpe(block: Block, slot: Slot, week: int) -> float | None:
    """The RPE this slot was prescribed at for a week, if it had one."""
    scheme = block.scheme_for(slot)
    if scheme and scheme.kind == "rpe_wave" and scheme.week_rpes:
        rpe = scheme.week_rpes[min(week, len(scheme.week_rpes)) - 1]
        if slot.intensity and slot.intensity.type == "rpe":
            rpe = min(rpe, slot.intensity.value)
        return rpe
    if slot.intensity and slot.intensity.type == "rpe":
        return slot.intensity.value
    return None


def _entry_rpe(entry: EntryLog) -> float | None:
    per_set = [st.rpe for st in entry.sets if st.rpe is not None]
    if per_set:
        return max(per_set)
    return entry.rpe


def _slot_for(block: Block, day: int | None, exercise: str, used: dict) -> Slot | None:
    """Ordered slot lookup that survives the same exercise appearing twice
    in a day (top single + backoff): each call consumes the next match."""
    for d in block.days:
        if day is not None and d.day != day:
            continue
        matches = [s for s in d.slots if s.exercise == exercise]
        if not matches:
            continue
        idx = used.get((d.day, exercise), 0)
        used[(d.day, exercise)] = idx + 1
        return matches[min(idx, len(matches) - 1)]
    return None


def rpe_drift(block: Block, sessions: list[SessionLog]) -> list[dict]:
    """Per week: mean(actual top RPE - planned RPE) over slots that had an
    RPE prescription. Positive drift = the plan is costing more than it
    should — the fatigue detector."""
    acc: dict[int, list[tuple[float, float]]] = {}
    for s in sessions:
        if s.block != block.id or s.week is None:
            continue
        used: dict = {}
        for e in s.entries:
            slot = _slot_for(block, s.day, e.exercise, used)
            if slot is None:
                continue
            planned = target_rpe(block, slot, s.week)
            actual = _entry_rpe(e)
            if planned is None or actual is None:
                continue
            acc.setdefault(s.week, []).append((planned, actual))
    out = []
    for week in sorted(acc):
        pairs = acc[week]
        planned = sum(p for p, _ in pairs) / len(pairs)
        actual = sum(a for _, a in pairs) / len(pairs)
        drift = actual - planned
        out.append(
            {
                "week": week,
                "n": len(pairs),
                "planned": round(planned, 2),
                "actual": round(actual, 2),
                "drift": round(drift, 2),
                "hot": drift >= HOT_DRIFT,
            }
        )
    return out


def red_flags(block: Block, sessions: list[SessionLog]) -> list[dict]:
    """Individual sets that demand coach attention: RPE >= 9.5, or reps
    below the bottom of the prescribed range (missed reps)."""
    flags: list[dict] = []
    for s in sessions:
        if s.block != block.id:
            continue
        used: dict = {}
        for e in s.entries:
            slot = _slot_for(block, s.day, e.exercise, used)
            for st in e.sets:
                rpe = st.rpe if st.rpe is not None else e.rpe
                if rpe is not None and rpe >= RED_FLAG_RPE:
                    flags.append(
                        {
                            "date": s.date,
                            "week": s.week,
                            "exercise": e.exercise,
                            "kind": "rpe",
                            "detail": f"{st.weight:g}x{st.reps} @RPE {rpe:g}",
                        }
                    )
                if slot and st.reps < bottom_reps(slot.reps):
                    flags.append(
                        {
                            "date": s.date,
                            "week": s.week,
                            "exercise": e.exercise,
                            "kind": "missed_reps",
                            "detail": f"{st.weight:g}x{st.reps} vs prescribed {slot.reps}",
                        }
                    )
    return flags


def weekly_load(sessions: list[SessionLog], catalog: dict[str, Exercise]) -> list[dict]:
    """ISO week -> total tonnage + top muscle contributions, oldest first."""
    ton = weekly_tonnage(sessions, catalog)
    out = []
    for wk in sorted(ton):
        muscles = ton[wk]
        total = sum(muscles.values())
        top = sorted(muscles.items(), key=lambda kv: -kv[1])[:5]
        out.append({"week": wk, "total": round(total), "top": [(m, round(v)) for m, v in top]})
    return out


def pain_context(
    pain_log: list[PainEvent],
    sessions: list[SessionLog],
    catalog: dict[str, Exercise],
) -> list[dict]:
    """For each pain event: how much load landed that ISO week on exercises
    touching the painful joint. Over time this exposes the 'knee complains
    when squat volume exceeds X' patterns."""
    out = []
    for p in pain_log:
        wk = p.date.isocalendar()
        load = 0.0
        for s in sessions:
            if s.date.isocalendar()[:2] != wk[:2]:
                continue
            for e in s.entries:
                ex = catalog.get(e.exercise)
                if ex and pain_touches(p, ex):
                    load += sum(st.weight * st.reps for st in e.sets)
        out.append(
            {
                "date": p.date,
                "location": p.location,
                "severity": p.severity,
                "open": p.resolved is None,
                "week_load_on_joint": round(load),
            }
        )
    return out


def block_response(block: Block, sessions: list[SessionLog]) -> list[dict]:
    """First vs. last e1RM inside the block, per exercise logged in it."""
    logs = [s for s in sessions if s.block == block.id]
    seen: list[str] = []
    for s in logs:
        for e in s.entries:
            if e.exercise not in seen:
                seen.append(e.exercise)
    out = []
    for ex in seen:
        hist = e1rm_history(logs, ex)
        if not hist:
            continue
        start, end = hist[0][1], hist[-1][1]
        delta = end - start
        out.append(
            {
                "exercise": ex,
                "points": len(hist),
                "e1rm_start": round(start, 1),
                "e1rm_end": round(end, 1),
                "delta": round(delta, 1),
                "delta_pct": round(delta / start, 4) if start else 0.0,
            }
        )
    return out


def _verdict(delta_pct: float, points: int) -> str:
    if points < 2:
        return "unknown"
    if delta_pct >= RESPONSE_THRESHOLD:
        return "responded"
    if delta_pct <= -RESPONSE_THRESHOLD:
        return "regressed"
    return "flat"


def build_review_scaffold(
    block: Block,
    sessions: list[SessionLog],
    catalog: dict[str, Exercise],
    pain_log: list[PainEvent],
) -> BlockReview:
    """Numeric skeleton of a block review. Verdicts are auto-suggested from
    the e1RM move; worked/failed/changes stay empty — that's judgment."""
    logs = [s for s in sessions if s.block == block.id]
    lifts = []
    for r in block_response(block, sessions):
        ex = catalog.get(r["exercise"])
        if ex and ex.category == "accessory":
            continue
        lifts.append(
            LiftReview(
                exercise=r["exercise"],
                e1rm_start=r["e1rm_start"],
                e1rm_end=r["e1rm_end"],
                verdict=_verdict(r["delta_pct"], r["points"]),
            )
        )
    drifts = rpe_drift(block, sessions)
    total_n = sum(d["n"] for d in drifts)
    avg_drift = (
        round(sum(d["drift"] * d["n"] for d in drifts) / total_n, 2) if total_n else None
    )
    ton = weekly_tonnage(logs, catalog)
    weekly_avg: dict[str, float] = {}
    if ton:
        for muscles in ton.values():
            for m, v in muscles.items():
                weekly_avg[m] = weekly_avg.get(m, 0.0) + v
        weekly_avg = {m: round(v / len(ton)) for m, v in weekly_avg.items()}
    end_date = block.start_date + timedelta(weeks=block.weeks)
    pains = [
        p
        for p in pain_log
        if p.block == block.id or block.start_date <= p.date < end_date
    ]
    return BlockReview(
        block=block.id,
        completed=logs[-1].date if logs else None,
        lifts=lifts,
        avg_rpe_drift=avg_drift,
        weekly_tonnage_avg=weekly_avg,
        pain_event_count=len(pains),
    )


def playbook_warnings(catalog: dict[str, Exercise]) -> list[str]:
    """Catalog hygiene: playbook swaps must point at real catalog ids."""
    out = []
    for ex in catalog.values():
        if not ex.playbook:
            continue
        for sid in ex.playbook.swaps:
            if sid not in catalog:
                out.append(f"{ex.id}: playbook swap '{sid}' not in catalog")
    return out
