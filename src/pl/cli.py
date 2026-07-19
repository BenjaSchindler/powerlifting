"""`pl` — command line for the training engine.

Claude drives this from chat; you can also run it yourself. Anything with
--json prints machine-readable output for the coach to reason over.
"""

from __future__ import annotations

import json
from datetime import date as Date
from pathlib import Path

import click

from . import analytics, insights, progression, storage
from .models import Block
from .sheet import build_csv, build_workbook, parse_any


def _load_all():
    root = storage.repo_root()
    return (
        root,
        storage.load_athlete(root),
        storage.load_exercises(root),
        storage.load_sessions(root),
        storage.load_pain_log(root),
    )


def _active_block(root) -> Block | None:
    blocks = storage.load_blocks(root)
    active = [b for b in blocks if b.status == "active"]
    return active[-1] if active else (blocks[-1] if blocks else None)


@click.group()
def main() -> None:
    """Powerlifting planner engine."""


@main.command()
def validate() -> None:
    """Parse every data file; fail loudly on schema drift."""
    root, athlete, catalog, sessions, pain = _load_all()
    blocks = storage.load_blocks(root)
    for s in sessions:
        for e in s.entries:
            if e.exercise not in catalog:
                click.echo(f"warn: session {s.date} uses unknown exercise '{e.exercise}'")
    for b in blocks:
        for d in b.days:
            for slot in d.slots:
                if slot.exercise not in catalog:
                    click.echo(f"warn: block {b.id} uses unknown exercise '{slot.exercise}'")
                if b.scheme_for(slot) is None and not (
                    slot.intensity and slot.intensity.type == "fixed"
                ):
                    click.echo(f"warn: block {b.id} slot {slot.exercise} has no scheme")
    for line in insights.playbook_warnings(catalog):
        click.echo(f"warn: {line}")
    reviews = storage.load_reviews(root)
    with_playbook = sum(1 for e in catalog.values() if e.playbook)
    click.echo(
        f"ok: athlete, {len(catalog)} exercises ({with_playbook} with playbook), "
        f"{len(blocks)} blocks, {len(sessions)} sessions, "
        f"{len(reviews)} reviews, {len(pain)} pain events"
    )


@main.command()
def status() -> None:
    """Where things stand: block, week, recent e1RMs, open pain flags."""
    root, athlete, catalog, sessions, pain = _load_all()
    block = _active_block(root)
    click.echo(f"athlete: {athlete.name} ({athlete.units}, inc {athlete.plate_increment})")
    if block:
        today = Date.today()
        week = min(max((today - block.start_date).days // 7 + 1, 1), block.weeks)
        click.echo(f"block:   {block.id} [{block.status}] week ~{week}/{block.weeks}")
        if block.sheet.drive_file_id:
            click.echo(f"sheet:   {block.sheet.title or ''} ({block.sheet.drive_file_id})")
    else:
        click.echo("block:   none — run the plan-block ritual")
    mains = [ex.id for ex in catalog.values() if ex.category == "main"]
    for ex_id in mains:
        e1, src = analytics.current_e1rm(sessions, ex_id, athlete, catalog=catalog)
        if e1 is not None:
            click.echo(f"e1rm:    {ex_id:<12} {e1:6.1f}  ({src})")
    for p in analytics.open_pain_flags(pain):
        click.echo(f"pain:    {p.location} {p.severity}/10 since {p.date.isoformat()} (open)")
    if sessions:
        click.echo(f"last session: {sessions[-1].date.isoformat()}")


@main.command()
@click.argument("exercise")
def e1rm(exercise: str) -> None:
    """e1RM history for one exercise."""
    root, athlete, catalog, sessions, _ = _load_all()
    ex_id = storage.resolve_exercise(exercise, catalog) or exercise
    hist = analytics.e1rm_history(sessions, ex_id)
    if not hist:
        click.echo(f"no logged sets for {ex_id}")
        return
    for d, v in hist[-20:]:
        click.echo(f"{d.isoformat()}  {v:6.1f}")


@main.command()
@click.argument("exercise", required=False)
def prs(exercise: str | None) -> None:
    """Rep PRs (heaviest weight per rep count)."""
    root, athlete, catalog, sessions, _ = _load_all()
    targets = (
        [storage.resolve_exercise(exercise, catalog) or exercise]
        if exercise
        else [ex.id for ex in catalog.values() if ex.category == "main"]
    )
    for ex_id in targets:
        table = analytics.rep_prs(sessions, ex_id)
        if not table:
            continue
        click.echo(ex_id)
        for reps, (w, d) in table.items():
            click.echo(f"  {w:6.1f} x {reps:<2} ({d.isoformat()})")


@main.command()
@click.option("--block", "block_id", default=None, help="block id (default: active block)")
@click.option("--week", type=int, required=True)
@click.option("--json", "as_json", is_flag=True)
def suggest(block_id: str | None, week: int, as_json: bool) -> None:
    """Deterministic targets for one week; Claude reviews warnings on top."""
    root, athlete, catalog, sessions, pain = _load_all()
    block = storage.load_block(block_id, root) if block_id else _active_block(root)
    if block is None:
        raise click.ClickException("no block found")
    targets = progression.suggest_week(block, week, sessions, athlete, catalog, pain)
    if as_json:
        click.echo(json.dumps([t.model_dump() for t in targets], indent=2, default=str))
        return
    cur_day = None
    for t in targets:
        if t.day != cur_day:
            cur_day = t.day
            click.echo(f"-- day {t.day}")
        w = f"{t.weight:g}" if t.weight is not None else "—"
        click.echo(f"{t.exercise:<18} {t.sets}x{t.reps:<5} @ {w:<7} {t.rationale}")
        for warn in t.warnings:
            click.echo(f"  !! {warn}")


@main.command("insights")
@click.option("--block", "block_id", default=None, help="block id (default: active block)")
@click.option("--json", "as_json", is_flag=True)
def insights_cmd(block_id: str | None, as_json: bool) -> None:
    """Pattern report: RPE drift, red-flag sets, load trend, pain context."""
    root, athlete, catalog, sessions, pain = _load_all()
    block = storage.load_block(block_id, root) if block_id else _active_block(root)
    report: dict = {}
    if block:
        report["block"] = block.id
        report["rpe_drift"] = insights.rpe_drift(block, sessions)
        report["red_flags"] = insights.red_flags(block, sessions)
        report["response"] = insights.block_response(block, sessions)
    report["weekly_load"] = insights.weekly_load(sessions, catalog)[-6:]
    report["pain_context"] = insights.pain_context(pain, sessions, catalog)
    if as_json:
        click.echo(json.dumps(report, indent=2, default=str))
        return

    if block is None:
        click.echo("no block — load trend and pain context only")
    else:
        click.echo(f"-- fatigue: RPE drift vs plan ({block.id})")
        drifts = report["rpe_drift"]
        if not drifts:
            click.echo("   no logged RPE-prescribed work yet")
        for d in drifts:
            mark = "  !! running hot" if d["hot"] else ""
            click.echo(
                f"   week {d['week']}: planned {d['planned']:g}, actual {d['actual']:g} "
                f"({d['drift']:+g} over {d['n']} entries){mark}"
            )
        if report["red_flags"]:
            click.echo("-- red flags (RPE >= 9.5 or missed reps)")
            for f in report["red_flags"]:
                click.echo(f"   {f['date']} {f['exercise']}: {f['detail']} [{f['kind']}]")
        resp = [r for r in report["response"] if r["points"] >= 2]
        if resp:
            click.echo("-- e1RM movement inside this block")
            for r in resp:
                click.echo(
                    f"   {r['exercise']:<18} {r['e1rm_start']:6.1f} -> {r['e1rm_end']:6.1f} "
                    f"({r['delta']:+g}, {r['delta_pct']:+.1%})"
                )
    if report["weekly_load"]:
        click.echo("-- weekly load (last 6 weeks)")
        for w in report["weekly_load"]:
            top = ", ".join(f"{m} {v / 1000:.1f}t" for m, v in w["top"][:3])
            click.echo(f"   {w['week']}: {w['total'] / 1000:.1f}t total | {top}")
    if report["pain_context"]:
        click.echo("-- pain vs load that week")
        for p in report["pain_context"]:
            state = "open" if p["open"] else "resolved"
            click.echo(
                f"   {p['date']} {p['location']} {p['severity']}/10 [{state}] — "
                f"{p['week_load_on_joint'] / 1000:.1f}t on that joint that week"
            )


@main.group()
def review() -> None:
    """Structured end-of-block reviews (the athlete response model)."""


@review.command("scaffold")
@click.option("--block", "block_id", required=True)
@click.option("--force", is_flag=True, help="overwrite an existing review.yaml")
def review_scaffold(block_id: str, force: bool) -> None:
    """Compute the numeric skeleton of review.yaml; judgment fields stay empty."""
    root, athlete, catalog, sessions, pain = _load_all()
    block = storage.load_block(block_id, root)
    path = storage.review_path(block.id, root)
    if path.exists() and not force:
        raise click.ClickException(f"{path} exists — edit it, or rerun with --force")
    rev = insights.build_review_scaffold(block, sessions, catalog, pain)
    storage.save_review(rev, root)
    click.echo(str(path))
    for lift in rev.lifts:
        click.echo(
            f"  {lift.exercise:<18} {lift.e1rm_start or 0:6.1f} -> {lift.e1rm_end or 0:6.1f}  {lift.verdict}"
        )
    click.echo("fill in: verdict corrections, worked/failed/changes_for_next")


@main.group()
def sheet() -> None:
    """Build and parse the gym sheet."""


@sheet.command("build")
@click.option("--block", "block_id", required=True)
@click.option("-o", "--out", type=click.Path(path_type=Path), default=None)
@click.option("--format", "fmt", type=click.Choice(["csv", "xlsx"]), default="csv",
              help="csv: upload via Drive create_file (becomes a Google Sheet)")
def sheet_build(block_id: str, out: Path | None, fmt: str) -> None:
    """Write the block sheet (csv for Drive upload, xlsx for local preview)."""
    root, athlete, catalog, sessions, pain = _load_all()
    block = storage.load_block(block_id, root)
    targets = progression.suggest_block(block, sessions, athlete, catalog, pain)
    out = out or root / "out" / f"{block.id}.{fmt}"
    if fmt == "csv":
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(build_csv(block, targets), encoding="utf-8")
    else:
        build_workbook(block, targets, out)
    click.echo(str(out))


@sheet.command("parse")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--block", "block_id", required=True)
@click.option("--week", "weeks", type=int, multiple=True, help="restrict to week(s)")
@click.option("--write", is_flag=True, help="save parsed sessions as YAML")
@click.option("--json", "as_json", is_flag=True)
def sheet_parse(file: Path, block_id: str, weeks: tuple[int, ...], write: bool, as_json: bool) -> None:
    """Turn a filled sheet export back into session logs."""
    root, athlete, catalog, sessions, _ = _load_all()
    block = storage.load_block(block_id, root)
    parsed = parse_any(file, block, list(weeks) or None)
    all_new = [s for wk in sorted(parsed) for s in parsed[wk]]
    if as_json:
        click.echo(json.dumps([s.model_dump(mode="json") for s in all_new], indent=2))
    for s in all_new:
        unknown = [e.exercise for e in s.entries if not storage.resolve_exercise(e.exercise, catalog)]
        if unknown:
            click.echo(f"warn: {s.date} unknown exercises: {unknown}")
        prs_found = analytics.find_new_prs(sessions, s)
        for line in prs_found:
            click.echo(f"PR! {line}")
        pains = [e.pain.location for e in s.entries if e.pain]
        if pains:
            click.echo(f"pain reported {s.date.isoformat()}: {pains} — log it in pain-log.yaml")
        if write:
            path = storage.save_session(s, root)
            click.echo(f"wrote {path.relative_to(root)}")
        else:
            click.echo(f"parsed {s.date.isoformat()} day {s.day}: {len(s.entries)} entries (dry run)")
