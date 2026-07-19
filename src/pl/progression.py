"""Weight suggestion engine.

The CLI computes deterministic targets from the schemes; Claude then layers
judgment on top (pain history, athlete feedback, life stress) and explains
any override in chat. Warnings emitted here are the hook for that judgment.
"""

from __future__ import annotations

from datetime import date as Date

from .analytics import current_e1rm, open_pain_flags, pain_touches, rpe_percent
from .models import Athlete, Block, Exercise, PainEvent, SessionLog, Slot, Target


def round_to_increment(weight: float, increment: float) -> float:
    if increment <= 0:
        return round(weight, 1)
    return round(round(weight / increment) * increment, 2)


def _last_result(sessions: list[SessionLog], block_id: str, exercise: str):
    """Most recent logged entry for this exercise inside this block."""
    for s in reversed(sessions):
        if s.block != block_id:
            continue
        for e in s.entries:
            if e.exercise == exercise and e.sets:
                return s, e
    return None, None


def _double_progression_weight(
    block: Block, slot: Slot, sessions: list[SessionLog], increment: float
) -> tuple[float | None, str]:
    scheme = block.scheme_for(slot)
    sess, entry = _last_result(sessions, block.id, slot.exercise)
    if entry is None:
        return None, "no history in this block yet — pick a weight that leaves 2-3 reps in reserve"
    top = block.top_reps(slot)
    last_weight = max(st.weight for st in entry.sets)
    all_at_top = all(st.reps >= top for st in entry.sets)
    quality = all(
        (st.rpe or entry.rpe or 0) <= (scheme.rep_quality_rpe if scheme else 8.0)
        for st in entry.sets
    )
    if all_at_top and quality:
        bumped = last_weight * (1 + (scheme.increment_pct if scheme else 0.025))
        w = max(round_to_increment(bumped, increment), last_weight + increment)
        return w, f"all sets hit {top} reps cleanly on {sess.date.isoformat()} — move up"
    return last_weight, f"keep {last_weight:g} and add reps toward {top} per set"


def suggest_week(
    block: Block,
    week: int,
    sessions: list[SessionLog],
    athlete: Athlete,
    catalog: dict[str, Exercise],
    pain_log: list[PainEvent] | None = None,
    today: Date | None = None,
) -> list[Target]:
    """Targets for every slot of one week of a block."""
    if not 1 <= week <= block.weeks:
        raise ValueError(f"week must be 1..{block.weeks}")
    pain_flags = open_pain_flags(pain_log or [], today=today)
    increment = athlete.plate_increment
    targets: list[Target] = []

    for day in block.days:
        for slot in day.slots:
            t = Target(
                week=week, day=day.day, exercise=slot.exercise, sets=slot.sets, reps=slot.reps
            )
            scheme = block.scheme_for(slot)
            kind = scheme.kind if scheme else None
            if slot.intensity and slot.intensity.type == "fixed":
                kind = "fixed"

            if kind == "fixed":
                t.weight = slot.intensity.value if slot.intensity else None
                t.rationale = "fixed prescription"
            elif kind in ("percent_wave", "rpe_wave") and scheme:
                if kind == "percent_wave":
                    pct = scheme.week_percents[min(week, len(scheme.week_percents)) - 1]
                    label = f"{pct:.0%} of e1RM"
                else:
                    rpe = scheme.week_rpes[min(week, len(scheme.week_rpes)) - 1]
                    if slot.intensity and slot.intensity.type == "rpe":
                        rpe = min(rpe, slot.intensity.value)
                    pct = rpe_percent(block.top_reps(slot), rpe)
                    label = f"{slot.reps} reps @RPE {rpe:g} (~{pct:.0%} e1RM)"
                base, src = current_e1rm(
                    sessions, slot.exercise, athlete, today=today, catalog=catalog
                )
                t.percent = round(pct, 4)
                if base is None:
                    t.rationale = f"{label} — but {src}"
                    t.warnings.append(f"no e1RM base for {slot.exercise}; set weight manually")
                else:
                    t.weight = round_to_increment(base * pct, increment)
                    t.rationale = f"{label} of {base:.1f} ({src})"
            elif kind == "double_progression":
                w, why = _double_progression_weight(block, slot, sessions, increment)
                t.weight, t.rationale = w, why
            elif slot.intensity and slot.intensity.type == "rpe":
                pct = rpe_percent(block.top_reps(slot), slot.intensity.value)
                base, src = current_e1rm(
                    sessions, slot.exercise, athlete, today=today, catalog=catalog
                )
                t.percent = round(pct, 4)
                if base is not None:
                    t.weight = round_to_increment(base * pct, increment)
                    t.rationale = f"@RPE {slot.intensity.value:g} (~{pct:.0%} of {base:.1f}, {src})"
                else:
                    t.rationale = f"@RPE {slot.intensity.value:g} — work up by feel ({src})"
            else:
                t.rationale = "no scheme — set by feel"

            if slot.exercise in catalog:
                ex = catalog[slot.exercise]
                for p in pain_flags:
                    if pain_touches(p, ex):
                        t.warnings.append(
                            f"open pain: {p.location} ({p.severity}/10 on {p.date.isoformat()})"
                            f" — loads {ex.joints}; hold or reduce load, review with coach"
                        )
            targets.append(t)
    return targets


def suggest_block(
    block: Block,
    sessions: list[SessionLog],
    athlete: Athlete,
    catalog: dict[str, Exercise],
    pain_log: list[PainEvent] | None = None,
    today: Date | None = None,
) -> dict[int, list[Target]]:
    """Targets for all weeks (used when printing a fresh block sheet).

    Double-progression slots only get a concrete number for week 1 — later
    weeks depend on logged performance and are decided week by week.
    """
    out: dict[int, list[Target]] = {}
    for week in range(1, block.weeks + 1):
        targets = suggest_week(block, week, sessions, athlete, catalog, pain_log, today)
        if week > 1:
            for t in targets:
                slot_scheme = _scheme_kind(block, t)
                if slot_scheme == "double_progression":
                    t.weight = None
                    t.rationale = "beat last week (weight or reps) — set after logging"
        out[week] = targets
    return out


def _scheme_kind(block: Block, target: Target) -> str | None:
    for day in block.days:
        if day.day != target.day:
            continue
        for slot in day.slots:
            if slot.exercise == target.exercise:
                s = block.scheme_for(slot)
                return s.kind if s else None
    return None
