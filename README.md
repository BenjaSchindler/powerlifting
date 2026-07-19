# powerlifting

Personal powerlifting planner where **Claude is the coach, this repo is the
memory, and a Google Sheet is the gym logbook**.

- Plans, logged sets, pain history and lessons live as YAML/Markdown in git.
- A Python engine (`pl`) computes e1RMs, progression targets and builds the
  block sheet; it also parses the filled sheet back into structured logs.
- Claude runs the rituals in chat: plan a block, ingest a training week,
  check in on pain/readiness, review a finished block.
- The Google Sheet stays dead simple: type your reps at the gym, nothing else.

See [docs/architecture.md](docs/architecture.md) for the design and
[CLAUDE.md](CLAUDE.md) for the coach's operating manual.

## The loop

1. **Plan** — tell Claude what's next (`/plan-block`). It drafts
   `data/blocks/<id>/block.yaml`, computes targets, uploads the sheet to
   Drive as a native Google Sheet.
2. **Train** — open the Sheet at the gym. One row per prescribed exercise,
   one `Reps | Kg | RPE` triplet per set (same dialect as the old coach
   sheets): type reps, leave Kg blank if you used the target, note RPE,
   and drop anything unusual in `Dolor`/`Notas`.
3. **Log** — after training (or weekly), `/log`. Claude downloads the
   sheet, `pl sheet parse --write` turns it into session YAML, PRs are
   announced, pain notes become pain-log entries, everything is committed.
4. **Adjust** — `/checkin` whenever something feels off. Claude adjusts the
   coming week in chat and records durable conclusions in `knowledge/`.

## Setup

```bash
uv sync          # install engine + dev deps
uv run pytest    # verify
uv run pl status # where things stand
```

## CLI cheatsheet

```bash
pl status                          # block, week, e1RMs, open pain flags
pl validate                        # parse all data files, warn on drift
pl e1rm squat                      # e1RM history for a lift
pl prs [exercise]                  # rep PRs
pl suggest --week 2 [--json]       # targets + warnings for a week
pl insights [--block <id>]         # RPE drift, red flags, load trend, pain context
pl review scaffold --block <id>    # numeric skeleton of the block review
pl sheet build --block <id>        # out/<id>.csv -> upload as Google Sheet
pl sheet parse f.csv --block <id> --write    # ingest a filled sheet
```

## Data map

| Path | What |
| --- | --- |
| `data/athlete.yaml` | profile, units, plate increment, known maxes |
| `data/exercises.yaml` | exercise catalog + muscles/joints/aliases + playbook (when to use what) |
| `data/blocks/<id>/block.yaml` | one training block: days, slots, schemes |
| `data/blocks/<id>/sessions/*.yaml` | what actually happened, set by set |
| `data/blocks/<id>/review.yaml` | structured block outcome (athlete response model) |
| `knowledge/pain-log.yaml` | structured pain events (drive the guardrails) |
| `knowledge/lessons.md` | dated conclusions with evidence |
| `knowledge/technique-cues.md` | per-lift cues |
