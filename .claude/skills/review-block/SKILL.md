---
name: review-block
description: End-of-block review — PRs, e1RM trends, volume tolerance, pain summary — distilled into lessons.md and seeds for the next block. Use when a block ends or the user asks how the block went.
---

# Review a finished block

## 1. Collect the evidence

- `uv run pl insights --block <id>` — RPE drift per week, red-flag sets,
  e1RM movement inside the block, load trend, pain-vs-load context.
- `uv run pl prs`, `uv run pl status`.
- Read every session YAML of the block and pain-log entries dated inside it.

## 2. Scaffold the structured review

- `uv run pl review scaffold --block <id>` → `data/blocks/<id>/review.yaml`
  with computed e1RM start/end and auto-suggested verdicts.
- Correct the verdicts where the numbers mislead (sick week, technique
  change, etc.) and fill `worked:`, `failed:`, `changes_for_next:` — with
  the athlete, in his words. These files accumulate into his personal
  response model; be honest, not polite.
- If a playbook rule proved wrong for him (a swap that didn't carry over, a
  variation that beat expectations), edit that exercise's `playbook:` in
  `data/exercises.yaml` — his evidence overrides the literature.

## 3. Write the review in chat (honest and short)

- e1RM movement per main lift (start → end, with the sets that prove it).
- What the athlete handled: sets/week per lift that progressed vs stalled.
- Pain timeline: what appeared, what resolved, what correlates.
- Plan adherence: skipped/modified sessions and why.

## 4. Persist the conclusions

- 2-5 dated bullets with evidence into `knowledge/lessons.md` — only
  things that should change future programming.
- Set the block's `status: done` in its block.yaml.
- Commit `review: <block-id>` and push.

## 5. Bridge

- End with: "for the next block this means …" (3 bullets max), then offer
  /plan-block.
