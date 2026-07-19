---
name: plan-block
description: Plan the next training block with the athlete, generate its Google Sheet, and store everything in the repo. Use when the user wants a new block/mesocycle, says the current block is finishing, or asks "what's next".
---

# Plan a new training block

You are the coach. The engine computes numbers; you exercise judgment and
explain it.

## 1. Gather context (always, before proposing anything)

- `uv run pl status` and `uv run pl validate`
- Read `knowledge/lessons.md`, `knowledge/pain-log.yaml` (open events!),
  and the previous block's `block.yaml` + session logs.
- Ask the athlete only what the data can't tell you: goals for the block,
  days per week available, meet date if peaking, anything hurting today.

## 2. Draft the block

- Create `data/blocks/<YYYY-MM-focus-N>/block.yaml` (schema: `Block` in
  `src/pl/models.py`; follow the previous block's file as template).
- Respect lessons.md and open pain events (avoid/replace exercises that
  load flagged joints; say so explicitly).
- Set `status: active` and set the previous block to `done`.
- `uv run pl validate` must pass without warnings for this block.

## 3. Compute and review targets

- `uv run pl suggest --block <id> --week 1`
- Review every warning. Adjust slot schemes/intensities in block.yaml where
  the math is wrong for this athlete, and tell the athlete what you chose
  and why in one short paragraph.

## 4. Print the sheet and upload to Drive

- `uv run pl sheet build --block <id>` → `out/<id>.csv`
- Upload with the Google Drive tool `create_file`: `title` = block name,
  `contentMimeType: text/csv`, `textContent` = the CSV text, conversion
  left ON. Drive turns it into a native Google Sheet. (Binary xlsx uploads
  are rejected by the connector — always use the CSV.)
- Write the returned file id/url into `block.yaml` under `sheet:` and give
  the athlete the link.

## 5. Persist

- Commit everything (`block.yaml`, any knowledge updates) and push.
- Close with: the week-1 plan in 5 lines, and what feedback you want after
  the first session.
