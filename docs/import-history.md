# Importing the historical coach sheets

Benjamin's 2024-season plan lives in a Google Sheet built from his old
coach's template ("HEAVY WEIGHT" community):

- File id: `1zr6KmiELHWlnkrUUF1KP_XXFezy03GnsTcrjZICgNTs`
- Layout: dashboard tab (calendar, RM ESTIMADOS, BEST) + one giant tab per
  season with `SEMANA n` sections; day headers like `LUNES SQ1 DL2`;
  prescription columns `Notas | Ejercicio | RPE | SERIES | REPS | KG Fijos |
  Sugerido` followed by up to 10 `REPS | KG | RPE` result triplets.
- Only a fraction of result cells are filled (squat and bench mostly; no
  deadlift results captured).

Known extracted highlights (2026-07, used to seed `athlete.yaml` notes):
SENTADILLA LB 220x3 @8 / 220x4 / 200x5 @6; SENTADILLA HB 215x1 @8;
PRESS BANCA COMP 100x3 @6; SIN PAUSA 100x6 @7; TEMPO 4.2.0 107.5x2 @6.

## How to import (when wanted)

The old format differs enough (merged cells, day codes, multiple seasons)
that a one-off conversational import beats writing a parser:

1. `read_file_content` the file (or export CSV per tab).
2. Claude walks season by season, building `data/blocks/<id>/block.yaml`
   retroactively (status: done) and `sessions/*.yaml` for rows that have
   logged results. Dates are approximate (week start + day offset from the
   calendar tab).
3. `pl validate`, then commit as `import: temporada 2024`.

This is optional — the system works without it; importing enriches PR
history and long-term e1RM trends.
