# Core Floods: a run page across all segments of a core flood, with per-sample flow, tube number and pore volumes

**Type:** feat
**Area:** `frontend/src/pages/CoreFloods/`, `backend/api/routers/core_floods.py`
**Priority:** high
**Related:** issue-result-entry-edit-delete.md (deferred), issue #97 (slot occupancy)

---

## Problem

A core flood run is split across several experiments, one per `-N` segment, and nothing shows them together. Experiment Detail covers one experiment (`TABS`, `frontend/src/pages/ExperimentDetail/index.tsx:18`), and no endpoint returns a whole chain.

The 2026-10-26 backup (`docs/sample_data/experiments_20261026_010002.sql`) shows:

- 78 Core Flood experiments under 29 base IDs, with 180 result rows. Many segments hold one sample (CF_027-2, CF_030-2 through CF_030-4).
- Changing flow forces a new experiment. CF_026-3 ("Stopped flow for ~1 week") exists only to record a hold.
- `conditions.flow_rate` (`database/models/conditions.py:71`) is set on 16 experiments, all older than CF_016. The frontend never shows it.
- Blanks sit inside the chain as `_Text` variants: CF_020-5_Bypass1, _Bypass2, _Background, _Background2, _Puddle, CF_023-3_Accumulator, CF_023-4_Bypass and CF_022_Fast. They inherit cumulative time.
- Several runs need cleanup:
  - CF_026 and CF_027 each have two roots (`-1` is a group-parent spelling).
  - CF_027-2 through CF_027-6 are all ONGOING in CF03, and CF_030-2 through CF_030-4 in CF02.
  - Naming is mixed (CF-05-1, CF-06-01, CF_016, CF_020_5_Brine).
- There is no pore volume field, and `core_volume_cm3` is 0 wherever it is set.

## Impact

Researchers can't read a run as one time series, can't record a hold or a flow change without creating an experiment, and can't see cumulative H2 or H2 per day against the 0.5 g/t/day target. Nothing links a result back to its physical sample tube.

## Fix

| # | Issue | Branch | Depends on |
|---|---|---|---|
| 1 | `issue-core-flood-schema-and-views.md` | `feat/core-flood-schema` | none |
| 2 | `issue-core-flood-api.md` | `feat/core-flood-api` | 1 |
| 3 | `issue-core-flood-frontend.md` | `feat/core-flood-run-page` | 2 |
| 4 | `issue-master-upload-tube-number.md` | `feat/master-upload-tube-number` | 1 |

Cut all branches from `develop` and open all PRs with `--base develop` (`gh pr create --base develop`).

Settled decisions (Mat, 2026-11-03):

1. **Page shape.** A standalone page: a list at `/core-floods` with active runs first and past runs searchable, then a run record at `/core-floods/:baseId`.
2. **Cleanup scope.** Rename, edit descriptions and set segment status, all through existing endpoints. Segments stay separate experiments; there is no merging.
3. **Flow rate.** Recorded per sample as `flow_rate_mL_min` on `experimental_results` (revised 2026-11-03 from a separate `core_flood_results` table). The value is the rate over the interval *ending* at that sample, and 0 means a hold. Flow only ever changes at a sample.
4. **Per-sample H2.** H2 µmol, H2 µg and H2 g/t keep coming from `scalar_calcs.py`, unchanged.
5. **Cross-sample values.** Interval days, cumulative liquid volume, pore volumes, cumulative H2 g/t and H2 g/t/day live in a view, `v_core_flood_samples`. Variants are excluded from them.
6. **Volume basis.** Volume is the measured liquid sample volume (`sampling_volume_mL`). Pore volumes = cumulative liquid volume / `pore_volume_mL`, a new conditions field the researcher enters.
7. **Tube number.** `sample_tube_number` lives on `ExperimentalResults`, for every experiment type. It is entered in the UI and also carried by the Master Results upload.
8. **Old flow field.** `conditions.flow_rate` stays in place, commented as deprecated, with no backfill.
9. **GC run date.** Defaults to the sample date and stays editable. On 34 of 109 historical CF rows it differs.
10. **H2 basis.** Each sample's H2 is only what was collected since the previous sample. So per-sample H2 g/t values can be summed into cumulative H2, and dividing by interval days gives H2 g/t/day.

**Sign-off gate:** sub-issues 1 and 4 change locked components:

- additive columns on `ExperimentalResults` and `ExperimentalConditions`
- an edit to the master parser

Mat picked these designs on 2026-11-03. Each PR description must cite that sign-off.

## Acceptance criteria

- [ ] "Core Floods" appears in the sidebar. It lists every core flood base ID, with active runs first
- [ ] A researcher can add a sample, edit a sample, fix a segment's name, description or status, and see cumulative H2 g/t, H2 g/t/day and pore volumes for any run, past or present
- [ ] A hold is entered as flow 0 on a sample and needs no new experiment
- [ ] Power BI can read `v_core_flood_samples`, and its values match what the run page shows

## Notes

Out of scope:

- Merging segments, editing a sample's day, deleting samples
- NH4 / NMR on the run page
- Checking measured volume against flow x time
- Dissolved H2 in brine
- Uploading the tracker's CF Flow and CF Sampling sheets
- The general result edit/delete epic
