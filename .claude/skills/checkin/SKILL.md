---
name: checkin
description: Free-form coach conversation — pain, fatigue, motivation, schedule changes. Records durable facts and adjusts the coming week. Use when the user reports how they feel, mentions pain outside logging, or asks to tweak the plan.
---

# Check-in

This is conversation first — listen, then persist what matters.

## 1. Ground yourself

- `uv run pl status`; read open entries in `knowledge/pain-log.yaml`.
- If he reports fatigue or grinding sets: `uv run pl insights` — the RPE
  drift section tells you whether it's one bad day or a hot trend.
- If pain rules an exercise out: the exercise's `playbook.swaps` in
  `data/exercises.yaml` is the pre-vetted swap list.

## 2. Listen and decide with them

Typical moves, always explained in plain words:

- **Pain report** → update/append `knowledge/pain-log.yaml`. If it loads
  an upcoming exercise (`pl suggest` warnings show this), propose the swap
  or load cap now, in chat — the sheet target stays as printed; tell them
  the revised number to write in the notes column.
- **Fatigue / bad sleep / life stress** → suggest reducing this week's top
  sets or converting a session; record in the session's `readiness:` when
  logged.
- **Schedule change** → reorder days in chat; only edit `block.yaml` if
  the structure changes permanently.

## 3. Persist

- Anything durable (a pattern, a resolution, a preference) → dated bullet
  in `knowledge/lessons.md`.
- Commit with `checkin: <topic>` and push if any file changed.
- Never end without telling them exactly what (if anything) changed for
  their next session.
