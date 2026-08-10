# New Experiments bulk upload never recalculated conditions derived fields

**Found:** 2026-08-10, investigating a missing Fe²⁺ %H₂ on `SERUM_Catalyst_001a-t3`.
**Status:** code fixed (`fix/bulk-upload-conditions-recalc`); data backfill see below.

## Symptom

`SERUM_Catalyst_001a-t3` had a complete H2 chain and no iron conversion:

```
h2_concentration = 353.88 ppm   gas_sampling_volume_ml = 30   gas_sampling_pressure_MPa = 0.101353
h2_micromoles    = 0.4415       h2_grams_per_ton_yield  = 0.8899
ferrous_iron_yield_h2_pct = NULL
```

Reported as a direct-injection problem, because the affected vials were all DI runs.

## Root cause

`water_to_rock_ratio` and `total_ferrous_iron_g` are stored derived fields written by
`recalculate_conditions()`. Every write path called `recalculate()` after mutating a
conditions row — `backend/api/routers/conditions.py:103` and `:125`,
`backend/api/routers/experiments.py:1329`, `database/lineage_utils.py:603` — except
`backend/services/bulk_uploads/new_experiments.py`, which creates or modifies
conditions rows in three places and only recalculated `ChemicalAdditive`.

`calculate_ferrous_iron_yield_h2` (`backend/services/calculations/scalar_calcs.py:24`)
returns None when `total_ferrous_iron_g` is None, so every scalar result under a
bulk-created experiment lost both Fe²⁺ yield percentages.

The tell was `water_to_rock_ratio` being NULL on the same row, with
`rock_mass_g = 1` and `water_volume_mL = 20`. Two computable derived fields both
empty means `recalculate()` never ran, not that an input was missing.

## Not a DI problem

`SERUM_Cation_001a-t5` is a DI row with the same 30 mL / 14.7 psi geometry and the
same sample `20250616_7`, and it *has* `ferrous_iron_yield_h2_pct = 0.0159%` — its
conditions row was recalculated by a later elemental upload via
`recalculate_conditions_for_samples`. The SERUM_Catalyst_001 vials were created
2026-07-24, after the last FeO upload for that sample, so nothing ever touched them.
The DI correlation is that the DI-era runs were all bulk-created.

## Production measurements (backup 2026-08-10 01:00)

Of 577 scalar rows with a computed `h2_micromoles`, 249 had no Fe²⁺ %H₂:

| Cause | Rows |
|---|---|
| `total_ferrous_iron_g` NULL, sample has FeO on record | 157 (144 experiments) |
| `total_ferrous_iron_g` NULL, sample has no FeO on record | 77 |
| `total_ferrous_iron_g` populated, scalar row stale | 15 |

845 of 1125 conditions rows had `total_ferrous_iron_g` NULL; 185 of those had **both**
derived fields NULL with positive rock mass and water volume.

## Fix

`_recalculate_touched_conditions(db, conditions_ids)` in `new_experiments.py` records
the primary key of every conditions row the upload touches — at all three write sites
— and recalculates them in one pass before returning, after every sheet has finished
mutating them. Keyed on primary keys because `db.expire_all()` runs after the
experiments-sheet loop and per-row savepoints can be rolled back after recording.
One try/except per row, so an unusable row does not cost the rest of the upload its
derived fields. The count appears in the upload's `info_messages`.

## Acceptance criteria

- [ ] A conditions-sheet row gets both derived fields computed by the upload.
- [ ] An `overwrite=TRUE` row that changes `rock_mass_g` recomputes both fields rather than keeping the stale values.
- [ ] A parent auto-copy row (no conditions sheet entry) gets its own derived fields.
- [ ] An experiment reaching conditions creation only via the additives sheet is recalculated.
- [ ] A bulk-created vial with a DI H2 reading ends up with a non-NULL `ferrous_iron_yield_h2_pct`.
- [ ] The 157 recoverable production rows have Fe²⁺ %H₂ after the backfill.
- [~] The 77 rows whose sample has no FeO on record cannot be fixed here — they need rock characterization uploaded first, which then triggers `recalculate_conditions_for_samples` automatically.

## Backfill

Filled in by Task 4.
