"""Data model for the training system.

Everything on disk is YAML that maps 1:1 to these models. The model doubles as
the knowledge graph: Exercise carries edges to muscles/joints/parent lifts,
SessionLog carries edges to Block/Exercise, PainEvent carries edges to
body location + Exercise + Block. Relations are followed by id lookups.
"""

from __future__ import annotations

from datetime import date as Date
from typing import Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- catalog


class Exercise(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    category: Literal["main", "variation", "accessory"] = "accessory"
    parent: Optional[str] = None  # variation of (e.g. pause-squat -> squat)
    pattern: Optional[str] = None  # squat / hinge / press / pull / core ...
    muscles: list[str] = Field(default_factory=list)
    joints: list[str] = Field(default_factory=list)
    unilateral: bool = False
    notes: Optional[str] = None


class MaxEntry(BaseModel):
    weight: float
    date: Optional[Date] = None
    source: Literal["tested", "estimated"] = "estimated"


class Athlete(BaseModel):
    name: str = "Athlete"
    units: Literal["kg", "lb"] = "kg"
    plate_increment: float = 2.5
    timezone: str = "America/Santiago"
    bodyweight: Optional[float] = None
    days_per_week: int = 4
    goals: list[str] = Field(default_factory=list)
    current_maxes: dict[str, MaxEntry] = Field(default_factory=dict)
    notes: Optional[str] = None


# --------------------------------------------------------------------------- planning


class Intensity(BaseModel):
    type: Literal["percent", "rpe", "fixed"] = "percent"
    value: float  # 0.75 for percent, 8 for rpe, 140.0 for fixed
    of: str = "e1rm"  # base for percent type


class Slot(BaseModel):
    exercise: str
    sets: int
    reps: str  # "5", "8-12", "5+" (AMRAP)
    intensity: Optional[Intensity] = None
    scheme: Optional[str] = None  # progression scheme id, else block default
    notes: Optional[str] = None


class DaySpec(BaseModel):
    day: int
    name: str
    slots: list[Slot] = Field(default_factory=list)


class Scheme(BaseModel):
    """How a slot progresses across the weeks of a block."""

    id: str
    kind: Literal["percent_wave", "rpe_wave", "double_progression", "fixed"]
    # percent_wave: one multiplier of e1RM per week, e.g. [0.725, 0.775, 0.825, 0.6]
    week_percents: list[float] = Field(default_factory=list)
    # rpe_wave: one target RPE per week, e.g. [6, 7, 8, 5]; kg comes from the
    # RPE chart (inverse Epley) applied to the current e1RM
    week_rpes: list[float] = Field(default_factory=list)
    # double_progression: add weight once all sets reach top of rep range at <= this RPE
    rep_quality_rpe: float = 8.0
    increment_pct: float = 0.025


class SheetRef(BaseModel):
    drive_file_id: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None


class Block(BaseModel):
    id: str  # e.g. 2026-08-strength-1
    name: str
    start_date: Date
    weeks: int
    focus: Literal["hypertrophy", "strength", "peaking", "gpp", "rehab"] = "strength"
    status: Literal["planned", "active", "done"] = "planned"
    notes: Optional[str] = None
    sheet: SheetRef = Field(default_factory=SheetRef)
    schemes: list[Scheme] = Field(default_factory=list)
    default_scheme: Optional[str] = None
    days: list[DaySpec] = Field(default_factory=list)

    def scheme_for(self, slot: Slot) -> Optional[Scheme]:
        sid = slot.scheme or self.default_scheme
        for s in self.schemes:
            if s.id == sid:
                return s
        return None

    def top_reps(self, slot: Slot) -> int:
        """Top of the rep range: '8-12' -> 12, '5' -> 5, '5+' -> 5."""
        rep = slot.reps.replace("+", "")
        parts = rep.split("-")
        return int(parts[-1])


# --------------------------------------------------------------------------- logging


class LoggedSet(BaseModel):
    weight: float
    reps: int
    rpe: Optional[float] = None


class PainNote(BaseModel):
    location: str
    severity: Optional[int] = None  # 0-10
    note: Optional[str] = None


class EntryLog(BaseModel):
    exercise: str
    sets: list[LoggedSet] = Field(default_factory=list)
    rpe: Optional[float] = None  # top-set RPE when per-set RPE is not recorded
    pain: Optional[PainNote] = None
    notes: Optional[str] = None


class SessionLog(BaseModel):
    date: Date
    block: Optional[str] = None
    week: Optional[int] = None
    day: Optional[int] = None
    entries: list[EntryLog] = Field(default_factory=list)
    readiness: dict[str, float | int | str] = Field(default_factory=dict)
    notes: Optional[str] = None


class PainEvent(BaseModel):
    date: Date
    location: str  # e.g. left_knee, lower_back
    severity: int = 0  # 0-10
    exercise: Optional[str] = None
    context: Optional[str] = None
    block: Optional[str] = None
    resolved: Optional[Date] = None  # date it stopped being an issue
    followups: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- suggestions


class Target(BaseModel):
    """A concrete prescription for one slot in one week, with reasoning."""

    week: int
    day: int
    exercise: str
    sets: int
    reps: str
    weight: Optional[float] = None
    percent: Optional[float] = None
    rationale: str = ""
    warnings: list[str] = Field(default_factory=list)
