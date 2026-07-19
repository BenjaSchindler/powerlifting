---
name: log
description: Ingest training results — from the gym Google Sheet or told in chat — into session YAML, update PRs and pain log, commit. Use after training sessions or weekly ("log my week", "I trained today", pasted results).
---

# Log training

## 1. Get the data

Preferred — the sheet: find `sheet.drive_file_id` in the active
`block.yaml`, then Drive `download_file_content` with
`exportMimeType: text/csv`; base64-decode to `out/filled.csv`.

Alternatively the athlete dictates results in chat — then write the
session YAML directly (schema: `SessionLog` in `src/pl/models.py`).

## 2. Parse and review before writing

- `uv run pl sheet parse out/filled.csv --block <id> --week <n>` (dry run)
- Look at what came out: unknown exercises? missing weights? PR lines?
  pain reports? Resolve ambiguities with the athlete, not by guessing.
- Re-run with `--write` once clean. Never overwrite an existing session
  file without telling the athlete.

## 3. Follow up like a coach

- Announce PRs plainly.
- Every pain mention becomes an entry in `knowledge/pain-log.yaml`
  (schema: `PainEvent`): ask location/severity if the sheet note is vague.
  Check existing open entries — same location within ~3 weeks is a
  `followups:` addition, not a new event; ask if old ones can be
  `resolved:`.
- RPE ≥ 9.5 on prescribed work, or missed reps → flag it and, if a pattern
  (2+ sessions), propose an adjustment for next week in chat.

## 4. Persist

- Commit data + knowledge changes with message `log: <block> W<n> D<n>`
  and push.
- Close with a 3-line summary: what was done vs plan, anything flagged,
  what's next on the sheet.
