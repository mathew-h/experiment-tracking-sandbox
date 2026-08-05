# bug: a blank `initial_note` on an overwrite row wipes the notes and inserts `"nan"`

> **Status 2026-08-05 — OPEN, not started.** Found during the code review of the
> issue #109 follow-up branch `fix/issue-109-bulk-rename-id-sync`, which is
> unrelated to this bug and deliberately does not fix it. The fix lands in
> `backend/services/bulk_uploads/new_experiments.py`, which is **LOCKED**
> (`docs/LOCKED_COMPONENTS.md`, CLAUDE.md §5), so it needs its own `/start-task`
> and explicit user sign-off before any edit.

## Summary

On a New Experiments upload row with `overwrite=TRUE` and an **empty**
`initial_note` cell, the parser does two wrong things in sequence: it deletes
every existing note for that experiment, and then inserts a replacement note
whose text is the literal string `"nan"`.

The researcher's intent for a blank cell is "don't touch the notes". What they
get is "destroy the notes and leave a placeholder". The note history is not
recoverable — `ExperimentNotes` rows are hard-deleted with
`synchronize_session=False` and no `ModificationsLog` snapshot is written for
them.

## Root cause

Two independent behaviors compound. Both are in
`backend/services/bulk_uploads/new_experiments.py`.

**1. A blank cell does not parse to `None`.** Line 452:

```python
initial_note = str(row.get('initial_note')).strip() if row.get('initial_note') is not None and str(row.get('initial_note')).strip() != '' else None
```

`pd.read_excel` represents an empty cell as `float('nan')`, not `None`. So
`row.get('initial_note') is not None` is **True**, and
`str(float('nan')).strip()` is the three-character string `'nan'`, which is not
`''`. Both guards pass and `initial_note` becomes `"nan"` — a truthy value.

The `date` field two blocks above gets this right, using `pd.isna(date_raw)`.
`initial_note` uses an `is not None` check instead, which NaN slips through.

**2. `overwrite=TRUE` clears the notes first, unconditionally.** Lines 636-640,
inside the overwrite branch and independent of whether `initial_note` has a
value:

```python
# Clear existing notes when overwrite=True (full data replacement)
db.query(ExperimentNotes).filter(
    ExperimentNotes.experiment_fk == experiment.id
).delete(synchronize_session=False)
```

Then lines 658-663 insert the replacement, gated only on truthiness:

```python
if initial_note:
    note = ExperimentNotes(
        experiment_fk=experiment.id,
        experiment_id=experiment.experiment_id,
        note_text=initial_note,
    )
```

Because (1) makes `initial_note` truthy for a blank cell, the guard at line 658
never protects the blank case. Had (1) been fixed alone, the overwrite would
still wipe the notes and simply leave none behind; had (2) been fixed alone, the
`"nan"` note would still be inserted. Both need addressing.

## Evidence

Measured against the local dev DB
(`postgresql://experiments_user:password@localhost:5432/experiments`) on
2026-08-05:

| Finding | Number |
|---|---|
| `experiment_notes` rows total | 1,131 across 921 experiments |
| Rows whose `note_text` is exactly `"nan"` (trimmed) | **4** |
| Same, case-insensitive | 4 (no other casing variants) |
| Other placeholder texts (`none`, `null`, `nat`, `n/a`, `-`, `0`) | 0 |

The four rows, all written in a single upload session:

| id | experiment_id | created_at |
|---|---|---|
| 619 | `OTHER_JW_002` | 2025-12-17 16:23 |
| 620 | `OTHER_JW_003` | 2025-12-17 16:23 |
| 621 | `OTHER_JW_004` | 2025-12-17 16:23 |
| 622 | `OTHER_JW_001` | 2025-12-17 16:24 |

Three of the four experiments (`OTHER_JW_002/003/004`) now hold **only** the
`"nan"` note. `OTHER_JW_001` holds two notes, one of them the `"nan"` row.

Whether any real note text was destroyed in that session cannot be recovered
from the database: the delete leaves no audit row. The blast radius is bounded
by how often `overwrite=TRUE` is used with a blank `initial_note`, which on this
data is 4 rows out of 1,131 — small, but the failure mode is silent and
destructive, so frequency is not the whole risk.

The mechanism is also now pinned by a test rather than left to be re-derived:
`tests/services/bulk_uploads/test_new_experiments_rename_denormalized_ids.py::test_bulk_rename_syncs_all_five_tables`
asserts that a blank `initial_note` on an overwrite row deletes the seeded note
and leaves exactly one note reading `"nan"`. That test documents current
behavior deliberately — **it will need updating as part of this fix**, and its
docstring points here.

## What is affected

- `POST /api/bulk-uploads/new-experiments` rows with `overwrite=TRUE` and an
  empty `initial_note` cell. Notes wiped, `"nan"` note inserted.
- Any consumer reading note text for display or reporting sees `"nan"` as if it
  were researcher-written content.

## What is NOT affected

- `overwrite` false/blank rows: the clearing block is inside the overwrite
  branch, so a create-path row with a blank `initial_note` still inserts a
  `"nan"` note but destroys nothing. (Worth confirming during the fix — the
  `"nan"` insert itself is not overwrite-gated.)
- The denormalized `experiment_id` on the inserted note is correct: it is taken
  from `experiment.experiment_id` after any rename, so this bug does not
  contribute to the stale-string problem tracked in
  `issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md`.
- Other bulk-upload sheets: the NaN-stringification pattern was found only on
  `initial_note`. Other blank-cell parses in this file either use `pd.isna` or
  an `isinstance(..., str)` guard, both of which reject NaN.

## Proposed fix (not implemented)

1. Guard the parse with `pd.isna(...)` the way the `date` field does, so a blank
   cell yields `None`.
2. Only clear existing notes when the row actually supplies replacement text —
   or, if "overwrite replaces notes" is the intended product behavior, keep the
   clear but write a `ModificationsLog` row recording what was removed, so the
   destruction is at least auditable.

Decision needed on (2): it is a product question, not just a parser bug. A blank
cell meaning "leave the notes alone" is the reading this issue assumes, but that
should be confirmed before the fix is written.

## Out of scope / next steps

Not fixed on `fix/issue-109-bulk-rename-id-sync`. That branch's sign-off covered
exactly one edit to this locked file (routing the rename through
`backend/services/denormalized_ids.py`), and CLAUDE.md §7 requires stopping
before any further bulk-upload parser change. Needs its own `/start-task`, a
decision on the product question above, and a data pass over the 4 known rows to
decide whether to null them or leave them as historical record.
