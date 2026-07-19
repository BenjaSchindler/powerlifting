---
name: plan-block
description: Plan the next training block with the athlete, generate its Google Sheet, and store everything in the repo. Use when the user wants a new block/mesocycle, says the current block is finishing, or asks "what's next".
---

# Plan a new training block

You are the coach. The engine computes numbers; you exercise judgment and
explain it.

## 1. Gather context (always, before proposing anything)

- `uv run pl status`, `uv run pl validate`, `uv run pl insights`
  (RPE drift and pain-vs-load patterns steer volume for the new block).
- Read `knowledge/lessons.md`, `knowledge/pain-log.yaml` (open events!),
  previous blocks' `review.yaml` files (what he responded to), and the
  previous block's `block.yaml` + session logs.
- Ask the athlete only what the data can't tell you: goals for the block,
  days per week available, meet date if peaking, anything hurting today.

## 2. Draft the block

- Create `data/blocks/<YYYY-MM-focus-N>/block.yaml` (schema: `Block` in
  `src/pl/models.py`; follow the previous block's file as template).
- Pick variations with the playbook (`playbook:` in `data/exercises.yaml`):
  match each slot's purpose to `use_when`, respect `avoid_when`, and take
  swaps from `swaps` when pain or equipment rules something out. Deviating
  from the playbook is fine — say why in chat and, if durable, fix the
  playbook entry.
- Respect lessons.md, review.yaml verdicts, and open pain events
  (avoid/replace exercises that load flagged joints; say so explicitly).
- Set `status: active` and set the previous block to `done`.
- `uv run pl validate` must pass without warnings for this block.

## 3. Compute and review targets

- `uv run pl suggest --block <id> --week 1`
- Review every warning. Adjust slot schemes/intensities in block.yaml where
  the math is wrong for this athlete, and tell the athlete what you chose
  and why in one short paragraph.

## 4. Print the sheet and get it into Drive

Preferred (pretty workbook, one tab per week):

- `uv run pl sheet build --block <id> --format xlsx` → `out/<id>.xlsx`
- Send the file to the athlete in chat and ask him to upload it to Drive
  (drag into drive.google.com; if it opens as .xlsx: Archivo → Guardar
  como hoja de cálculo de Google). The connector rejects binary uploads,
  so he is the upload step.
- When he passes the link/confirms, write the file id/url into
  `block.yaml` under `sheet:` (get the id from the URL or `search_files`).

Fallback (zero manual steps, single tab): `uv run pl sheet build --block
<id>` → CSV; Drive `create_file` with `textContent` = CSV text,
`contentMimeType: text/csv`, conversion ON; store returned id/url.

## 5. Persist

- Commit everything (`block.yaml`, any knowledge updates) and push.
- Close with: the week-1 plan in 5 lines, and what feedback you want after
  the first session.
