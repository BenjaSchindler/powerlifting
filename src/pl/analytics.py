"""Derived numbers: e1RM, PRs, tonnage, pain flags.

Pure functions over the loaded models — no I/O here.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import timedelta

from .models import Athlete, Exercise, LoggedSet, PainEvent, SessionLog

E1RM_WINDOW_DAYS = 60  # how far back a set still says something about today


def epley_e1rm(weight: float, reps: int, rpe: float | None = None) -> float:
    """Estimated 1RM. With RPE, credit reps left in the tank (RIR = 10 - RPE)."""
    if reps <= 0 or weight <= 0:
        return 0.0
    effective = reps + (10.0 - rpe if rpe is not None else 0.0)
    if effective <= 1:
        return weight
    return weight * (1.0 + effective / 30.0)


def rpe_percent(reps: int, rpe: float) -> float:
    """Fraction of 1RM for `reps` at target `rpe` — inverse of epley_e1rm,
    so suggestions and estimates stay consistent (same idea as the RTS /
    plsource RPE chart)."""
    effective = reps + (10.0 - rpe)
    if effective <= 1:
        return 1.0
    return 1.0 / (1.0 + effective / 30.0)


def _sets_for(sessions: list[SessionLog], exercise: str):
    for s in sessions:
        for e in s.entries:
            if e.exercise != exercise:
                continue
            for st in e.sets:
                yield s.date, LoggedSet(weight=st.weight, reps=st.reps, rpe=st.rpe or e.rpe)


def current_e1rm(
    sessions: list[SessionLog],
    exercise: str,
    athlete: Athlete | None = None,
    today: Date | None = None,
    catalog: dict[str, Exercise] | None = None,
) -> tuple[float | None, str]:
    """Best recent e1RM and where it came from.

    Order: logged sets in the window -> athlete.current_maxes ->
    parent lift's max (variations, marked clearly) -> None.
    """
    today = today or Date.today()
    cutoff = today - timedelta(days=E1RM_WINDOW_DAYS)
    best, best_src = None, ""
    for d, st in _sets_for(sessions, exercise):
        if d < cutoff:
            continue
        est = epley_e1rm(st.weight, st.reps, st.rpe)
        if best is None or est > best:
            best, best_src = est, f"{st.weight}x{st.reps} on {d.isoformat()}"
    if best is not None:
        return best, f"e1RM from {best_src}"
    if athlete and exercise in athlete.current_maxes:
        m = athlete.current_maxes[exercise]
        return m.weight, f"{m.source} max in athlete.yaml"
    if athlete and catalog and exercise in catalog and catalog[exercise].parent:
        parent = catalog[exercise].parent
        base, src = current_e1rm(sessions, parent, athlete, today, catalog)
        if base is not None:
            return base, f"UNSCALED parent ({parent}) base — adjust: {src}"
    return None, "no data"


def e1rm_history(sessions: list[SessionLog], exercise: str) -> list[tuple[Date, float]]:
    """Best e1RM per training day, oldest first."""
    per_day: dict[Date, float] = {}
    for d, st in _sets_for(sessions, exercise):
        est = epley_e1rm(st.weight, st.reps, st.rpe)
        per_day[d] = max(per_day.get(d, 0.0), est)
    return sorted(per_day.items())


def rep_prs(sessions: list[SessionLog], exercise: str) -> dict[int, tuple[float, Date]]:
    """Heaviest weight ever done for each rep count."""
    prs: dict[int, tuple[float, Date]] = {}
    for d, st in _sets_for(sessions, exercise):
        cur = prs.get(st.reps)
        if cur is None or st.weight > cur[0]:
            prs[st.reps] = (st.weight, d)
    return dict(sorted(prs.items()))


def find_new_prs(history: list[SessionLog], new_session: SessionLog) -> list[str]:
    """Human-readable PR lines that new_session sets vs. prior history."""
    out: list[str] = []
    for e in new_session.entries:
        prior = rep_prs(history, e.exercise)
        best_new: dict[int, float] = {}
        for st in e.sets:
            best_new[st.reps] = max(best_new.get(st.reps, 0.0), st.weight)
        for reps, w in sorted(best_new.items()):
            old = prior.get(reps)
            if old is None or w > old[0]:
                was = f" (was {old[0]:g})" if old else ""
                out.append(f"{e.exercise}: {w:g} x {reps} rep PR{was}")
    return out


def weekly_tonnage(
    sessions: list[SessionLog], catalog: dict[str, Exercise]
) -> dict[str, dict[str, float]]:
    """ISO-week -> muscle -> total kg lifted. The fatigue map."""
    out: dict[str, dict[str, float]] = {}
    for s in sessions:
        wk = f"{s.date.isocalendar().year}-W{s.date.isocalendar().week:02d}"
        for e in s.entries:
            muscles = catalog[e.exercise].muscles if e.exercise in catalog else ["unknown"]
            vol = sum(st.weight * st.reps for st in e.sets)
            for m in muscles:
                out.setdefault(wk, {})[m] = out.setdefault(wk, {}).get(m, 0.0) + vol
    return out


def open_pain_flags(
    pain_log: list[PainEvent], today: Date | None = None, window_days: int = 21
) -> list[PainEvent]:
    """Unresolved pain events recent enough to still steer programming."""
    today = today or Date.today()
    cutoff = today - timedelta(days=window_days)
    return [p for p in pain_log if p.resolved is None and p.date >= cutoff]


def pain_touches(pain: PainEvent, exercise: Exercise) -> bool:
    """Does this pain location involve a joint this exercise loads?"""
    loc = pain.location.lower()
    return any(j.lower() in loc for j in exercise.joints)
