# Replicate Group H2 Calculation — Testing Findings

## Summary

Scope: end-to-end testing of the hydrogen-only calculation chain (`h2_micromoles`,
`h2_mass_ug`, `h2_grams_per_ton_yield`, `ferrous_iron_yield_h2_pct`) for a lettered
replicate group (`a`/`b`/`c`), plus the group rollup endpoint
(`GET /api/experiments/{experiment_id}/rollup`, backed by `v_results_scalar_rollup`).
Read-only investigation — no application code, migrations, views, or config were
modified. All writes were test data entered through the running app (UI forms, one
`fetch()` call to `GET /rollup` using the app's own session token).

**App under test:** frontend dev server `http://localhost:5173` (proxying to backend
`http://localhost:8000`), logged in as `labpc@addisenergy.com`.

**Test experiments created (delete after review):**

| Experiment | DB id (`experiments.id`) | Role |
|---|---|---|
| `HPHT_901` | 729 | Group parent ("replicate 0"), sample `Tamarack`, rock_mass_g=10, day-7 H2 result (extreme value, inclusion probe) |
| `HPHT_901a` | 730 | Replicate a — day 7 + day 14 H2 results |
| `HPHT_901b` | 731 | Replicate b — day 7 + day 14 H2 results |
| `HPHT_901c` | 732 | Replicate c — day 7 H2 result only |
| `HPHT_901d` | 733 | Replicate d — day 7 result with **no** H2 data (missing-value probe) |
| `HPHT_902` | 734 | Standalone (non-replicate) single-experiment group, day 5 H2 result |

Conditions were identical across the whole `HPHT_901` group and `HPHT_902`
(`rock_mass_g=10`, `water_volume_mL=100`, `temperature_c=220`, sample `Tamarack`,
`total_ferrous_iron_g=0.8161746283614497` computed from Tamarack's characterized
FeO=10.5%). All results were entered via the "Add Results" modal on each
experiment's Results tab; NH₄/pH/conductivity fields were left blank throughout
(hydrogen-only per test scope).

Raw inputs entered (all via the modal's "Gas sampling pressure (PSI)" field, which
the frontend converts to MPa before sending to the API):

| Experiment | Day | H₂ (ppm) | Pressure (psi → MPa) | Vol (mL) |
|---|---|---|---|---|
| HPHT_901 (parent) | 7 | 50000 | 100 → 0.689476 | 20 |
| HPHT_901a | 7 | 5000 | 100 → 0.689476 | 20 |
| HPHT_901a | 14 | 3000 | 80 → 0.5515808 | 15 |
| HPHT_901b | 7 | 8000 | 100 → 0.689476 | 20 |
| HPHT_901b | 14 | 4000 | 80 → 0.5515808 | 15 |
| HPHT_901c | 7 | 6500 | 100 → 0.689476 | 20 |
| HPHT_901d | 7 | (none entered) | (none) | (none) |
| HPHT_902 | 5 | 4500 | 100 → 0.689476 | 20 |

**Bottom line:** the per-replicate H2 calculation chain itself is correct in every
case checked (see Finding #6 / "no bug"). The group **rollup** feature is broken for
any data entered through the normal "Add Results" UI flow — `time_post_reaction_bucket_days`
is never populated by that code path, so `GET /rollup` collapses an entire replicate
group's whole history (every timepoint, every replicate, **and the parent**) into one
undifferentiated row instead of one row per day. On top of that, the parent's own
data is folded into the aggregate with no way to exclude it, and even the intended
per-day math is not what a user would expect.

---

## Findings

| # | Severity | Where | Summary |
|---|---|---|---|
| 1 | **Blocker** | API / calc engine (`backend/api/routers/results.py::create_result`) | `POST /api/results` never sets `time_post_reaction_bucket_days` |
| 2 | **Blocker** (consequence of #1) | Rollup view / API | `GET /rollup` returns a single `bucket=null` row lumping all timepoints together instead of one row per day |
| 3 | **Major** | Rollup view / API, undocumented | The bare parent ("replicate 0")'s own scalar data is folded into the group aggregate, indistinguishable from lettered replicates |
| 4 | **Minor** | UI (Results tab, Grouped view) | Rollup summary table omits `H₂ (g/t)` and `Fe²⁺ → H₂ (%)` mean±sd columns even though both are selectable chart metrics and returned by the API |
| 5 | **Minor**, unconfirmed root cause, adjacent to scope | Rollup view SQL | `mean_net_ammonium_mM`/`sd_net_ammonium_mM` show `0.00 ± 0.00` instead of "no data" when no row in the group has any ammonium measurement |

### 1. `POST /api/results` never populates `time_post_reaction_bucket_days` — Blocker — API / calc engine

**Where it surfaces:** API (`POST /api/results`), and therefore every downstream
consumer of `time_post_reaction_bucket_days` (the rollup view, the per-experiment
"Grouped" chart/table).

**Reproduction:**
1. Open any experiment → Results tab → "+ Add Results".
2. Enter a "Time post reaction (days)" value (e.g. `7`) and any H₂ inputs. Save.
3. `GET /api/experiments/{id}/results` for that experiment.

**Observed:** the created row has `"time_post_reaction_days": 7.0` but
`"time_post_reaction_bucket_days": null`. Confirmed on all 8 results created in this
session (both `HPHT_901a` timepoints, both `HPHT_901b` timepoints, `HPHT_901`,
`HPHT_901c`, `HPHT_901d`, `HPHT_902`) — every single one has `time_post_reaction_bucket_days: null`
despite a correctly-stored `time_post_reaction_days`.

**Expected:** `time_post_reaction_bucket_days` should mirror `time_post_reaction_days`
(rounded per `normalize_timepoint()`, 4 decimal places — see
`backend/services/result_merge_utils.py`), the same way it does for bulk-uploaded
data.

**Root cause (read, not modified):** `backend/api/routers/results.py::create_result`
(lines 76–104) builds `ExperimentalResults(**data)` directly from the
`ResultCreate` payload. `data["time_post_reaction_days"]` is explicitly resolved via
`apply_id_timepoint(...)`, but nothing ever computes or assigns
`time_post_reaction_bucket_days` — the field is simply whatever the frontend sent
(nothing), so it defaults to `None`. Compare with
`backend/services/scalar_results_service.py` / `backend/services/result_merge_utils.py`,
where every code path (bulk uploads, merges) explicitly calls
`normalize_timepoint()` to set this field. `POST /api/results` — the endpoint behind
the UI's only "Add Results" affordance — is the one creation path that skips it.
There is no `PATCH` endpoint for `ExperimentalResults` either, so once created via
this modal, a result's bucket day can never be fixed through the UI.

**Evidence — request/response for `HPHT_901a`, day 7:**
```
POST /api/results/scalar
→ {"result_id":1540,...}
GET /api/experiments/HPHT_901a/results
→ {"id":1540,...,"time_post_reaction_days":7.0,"time_post_reaction_bucket_days":null,...}
```
and day 14 on the same experiment:
```
→ {"id":1545,...,"time_post_reaction_days":14.0,"time_post_reaction_bucket_days":null,...}
```

**Cross-check against existing production-style data:** `HPHT_097` (an existing,
non-test experiment with a long result history, presumably populated via bulk
upload) has `time_post_reaction_bucket_days` correctly populated and equal to
`time_post_reaction_days` on every row (`1.0`, `3.0`, `4.0`, `6.0`, `8.0`, `11.0`,
`15.0`, `19.0`). This confirms the bug is specific to the manual "Add Results" UI
path, not a general/global data corruption — but it does mean **every experiment
whose timepoints were entered by hand through the UI** (which, for a small
day-to-day lab team adding a result as soon as a sample comes back, is presumably
the common case — not the bulk-upload path) will have broken bucketing.

---

### 2. Rollup endpoint collapses the whole group history into one row — Blocker — Rollup view / API

**Where it surfaces:** `GET /api/experiments/{experiment_id}/rollup`; the
"Grouped" tab on any experiment's Results page.

**Reproduction:** open `HPHT_901a` → Results → "Grouped (n=4)" (or call
`GET /api/experiments/HPHT_901/rollup` / `.../HPHT_901a/rollup` directly — both
resolve to the same group key and return identically).

**Observed** (full response body):
```json
[{"base_experiment_id":"HPHT_901","time_post_reaction_bucket_days":null,"n_replicates":7,
  "mean_gross_ammonium_mM":null,"median_gross_ammonium_mM":null,"sd_gross_ammonium_mM":null,
  "mean_net_ammonium_mM":0.0,"sd_net_ammonium_mM":0.0,
  "mean_h2_micromoles":69.49333004532467,"sd_h2_micromoles":105.38714992733354,
  "mean_h2_grams_per_ton":14.009021417176909,"sd_h2_grams_per_ton":21.244784779551317,
  "mean_fe_yield_h2_pct":1.4264796582218013,"sd_fe_yield_h2_pct":2.163266971251243,
  "mean_fe_yield_nh3_pct":null,"sd_fe_yield_nh3_pct":null,
  "mean_grams_per_ton_yield":null,"sd_grams_per_ton_yield":null,"mean_final_ph":null}]
```
Only **one row** is returned, for the whole group, for all time — `n_replicates: 7`
is the count of every scalar row across the entire `HPHT_901` family (parent day-7,
a's day-7 and day-14, b's day-7 and day-14, c's day-7, d's day-7 with no H2 = 7 rows).

**Expected** (this is a direct consequence of Finding #1 — with bucketing working,
the same underlying per-row data should produce two separate rows). Hand-computed
from the raw per-row values (`GET /api/experiments/HPHT_901a/results` etc., since
the buggy endpoint cannot produce these itself):

| bucket day | contributing rows | n_replicates | mean H₂ (µmol) | sd H₂ (µmol) |
|---|---|---|---|---|
| 7 | parent (282.877), a (28.288), b (45.260), c (36.774), d (null) | 5 | ≈98.30 | ≈123.25 |
| 14 | a2 (10.184), b2 (13.578) | 2 | ≈11.88 | ≈2.40 |

Instead, the actual single lumped row mixes day-7 and day-14 data together
(mean 69.49, sd 105.39 — a number that corresponds to nothing a researcher actually
measured on any single day) and gives no way to see day-7 vs. day-14 separately.

**UI symptom:** with `time_post_reaction_bucket_days: null`, the chart component has
no x-value to plot the point at — the chart renders completely blank (no line, no
points, no "no data" message), while the table below it silently shows the one
lumped row with `TIME (D)` displayed as `—`. See screenshot evidence: the "Grouped"
view for `HPHT_901a` shows an empty plot area and a single table row with time `—`,
`n = 7`.

---

### 3. Parent ("replicate 0") data is silently included in the group aggregate — Major — Rollup view, undocumented behavior

**Where it surfaces:** `v_results_scalar_rollup` (and therefore `GET /rollup`).

**Reproduction:** give the bare parent experiment (`HPHT_901`) its own H2 result,
distinct from its lettered children, then call `GET /rollup` for any member of the
group.

**Observed:** I gave the parent an extreme, easily-identified H2 value (50000 ppm,
10× replicate a's 5000 ppm, same pressure/volume) specifically so its contribution
would stand out. The returned `mean_h2_micromoles` (69.49333004532467) is **exactly**
the arithmetic mean of the 6 non-null `h2_micromoles` values across the whole
group — including the parent's 282.877 µmol:
```
(282.87651307459157 + 28.28765130745916 + 10.183554470685294 + 45.26024209193465
 + 13.578072627580395 + 36.7739466996969) / 6 = 69.49333004532466
```
This matches the API's returned value bit-for-bit. Excluding the parent, the mean of
the remaining 5 values would be ≈26.82 µmol — roughly **4× smaller**. The parent's
outlier value alone is what drags `sd_h2_micromoles` up to 105.39.

**Expected / ambiguity:** neither `MODELS.md` nor `docs/api/API_REFERENCE.md`
documents whether the parent's own measurements are supposed to be part of the
rollup aggregate. The grouping key is `COALESCE(base_experiment_id, experiment_id)`;
because the parent's own `base_experiment_id` resolves to its own `experiment_id`
(confirmed via `GET /api/experiments/HPHT_901` — `base_experiment_id` is not `NULL`,
it equals `"HPHT_901"` for the parent itself, and likewise `HPHT_902`'s standalone
`base_experiment_id` is `"HPHT_902"`), the parent's rows land in the exact same
group as its lettered children **by construction**, with no `is_outlier`-style flag
or opt-out. In real lab usage, the bare/parent ID is very often where a researcher
runs the "original" experiment before deciding to spin off replicates — its
conditions and results are not necessarily a fourth "true" replicate of the same
run. Silently averaging it in (with zero visual indication beyond a `"replicate 0"`
chart legend entry that's easy to miss) can materially skew the reported mean/std a
user relies on for replicate QA.

This is independent of Finding #1/#2 — even if bucketing worked perfectly, the
day-7 bucket would still merge the parent's row with a/b/c/d's.

---

### 4. Grouped rollup table omits H₂ (g/t) and Fe²⁺→H₂ (%) columns — Minor — UI

**Where it surfaces:** Results tab → "Grouped" view, summary table under the chart.

**Reproduction:** open the "Grouped" view for any replicate group; open the
"METRIC" dropdown.

**Observed:** the METRIC dropdown offers 8 selectable series: `Gross NH₄ (mM)`,
`Net NH₄ (mM)`, `NH₄ (g/t)`, `H₂ (µmol)`, `H₂ (g/t)`, `Fe²⁺ → H₂ (%)`,
`Fe²⁺ → NH₃ (%)`, `pH`. The table beneath the chart, however, always shows a fixed
set of only 8 *columns* — but they are not the same 8: `TIME (D)`, `N`,
`GROSS NH₄ (MM)`, `NET NH₄ (MM)`, `NH₄ (G/T)`, `H₂ (µMOL)`, `FE²⁺ → NH₃ (%)`, `PH`.
`H₂ (g/t)` and `Fe²⁺ → H₂ (%)` are selectable in the chart but never appear in the
table, regardless of which metric is selected — even though the `/rollup` API
response includes `mean_h2_grams_per_ton`/`sd_h2_grams_per_ton` and
`mean_fe_yield_h2_pct`/`sd_fe_yield_h2_pct` on every row.

**Expected:** for a task whose entire premise is comparing H2-derived yields across
replicates, the two most relevant derived numbers (H₂ g/t and Fe²⁺→H₂%) are only
ever visible as a chart line (readable by hovering/eyeballing), never as a
numeric mean±sd — inconsistent with how `Fe²⁺ → NH₃ (%)` (the NH3-side equivalent)
*is* tabulated.

---

### 5. `mean_net_ammonium_mM` shows `0.00 ± 0.00` instead of "no data" — Minor, unconfirmed root cause, adjacent to H2 scope

Not part of the requested hydrogen-only scope, but directly observed on the same
view under test, so flagging it rather than silently ignoring it.

**Observed:** every contributing row in the `HPHT_901` group has
`gross_ammonium_concentration_mM: null` (no NH4 was ever entered — hydrogen-only
per test design). The rollup response nonetheless reports
`"mean_net_ammonium_mM": 0.0, "sd_net_ammonium_mM": 0.0` rather than `null`.

**Suspected root cause (read, not modified, not independently verified against the
live database engine):** `database/event_listeners.py`'s
`v_results_scalar_rollup` computes
`AVG(GREATEST(0, gross_ammonium_concentration_mM - background_ammonium_concentration_mM))`.
In PostgreSQL, `GREATEST()` ignores `NULL` arguments and returns the greatest
non-`NULL` one — so `GREATEST(0, NULL)` evaluates to `0`, not `NULL`. If this
environment's rollup view is indeed running on Postgres (per `CLAUDE.md`'s "current
state" table — `MODELS.md` still describes the schema as "deployed on SQLite",
which appears to be stale documentation, since SQLite's multi-argument `max()`
would instead propagate `NULL`), this would mean "never measured" and "measured
exactly at background level" become indistinguishable in every rollup — always
reported as `0 mM`, never as blank/no-data. I have not chased this further since
it's outside the requested H2-only scope, and I have not confirmed which database
engine this environment is actually running against — noting it here as something
worth a dedicated follow-up rather than as a confirmed, root-caused bug.

---

## What worked correctly (no bug found)

- **Per-replicate H2 calculation chain** — `h2_micromoles`, `h2_mass_ug` (implied by
  `h2_grams_per_ton_yield`), `h2_grams_per_ton_yield`, and `ferrous_iron_yield_h2_pct`
  matched the documented formulas (`docs/CALCULATIONS.md`) in every one of the 8
  results created, across 5 distinct `h2_concentration`/pressure/volume
  combinations. Spot-checked the PV=nRT chain by hand (P_atm = MPa×9.86923,
  V_L = mL/1000, n = PV/RT at T=293.15K, R=0.082057) and the Fe²⁺ stoichiometry
  (3 mol Fe²⁺ : 1 mol H₂, Fe molar mass 55.845 g/mol) for `HPHT_901a` (5000 ppm):
  predicted `h2_micromoles≈28.28`, actual `28.28765130745916`; predicted
  `ferrous_iron_yield_h2_pct≈0.4211%` (using an earlier, less precise pressure
  assumption) recomputed exactly against the actual stored MPa (`0.689476`,
  derived from the UI's 100 psi input) gives `0.5806565772951704%`, an exact match.
  A 10× linearity check (parent's 50000 ppm vs. replicate a's 5000 ppm, identical
  pressure/volume) produced outputs exactly 10× larger across all four derived
  fields, as expected from the linear PV=nRT relationship.
- **`total_ferrous_iron_g` resolution** — correctly resolved via the sample
  characterization lookup (`Tamarack`, FeO=10.5%) to `0.8161746283614497` g for
  `rock_mass_g=10`, matching `docs/CALCULATIONS.md`'s formula
  (`FeO_wt% / 100 × 0.777309 × rock_mass_g`) to full precision, and was identical
  across every experiment that copied conditions from the `HPHT_901` parent (as
  expected, since replicate-creation copies conditions verbatim) as well as the
  independently-created `HPHT_902` (same sample, same rock mass).
- **PSI→MPa conversion** in the "Add Results" modal — 100 psi consistently stored
  as exactly `0.689476` MPa, 80 psi as `0.5515808` MPa (standard 1 psi = 0.00689476
  MPa factor), correctly applied before being sent to the API.
- **Missing-H2 replicate (`HPHT_901d`)** — submitting the "Add Results" form with
  H2 fields left blank does create a `scalar_results` row (not skipped/omitted),
  with all H2-derived fields correctly `null`. The rollup view's
  `COUNT(sr.result_id)` includes this row in `n_replicates` (since a scalar row
  exists), while `AVG()`/`stddev_samp()` correctly exclude its `NULL` H2 values
  from the H2-specific means/stds — no crash, no `NaN`. Worth noting as a UX
  caveat rather than a bug: the single `n` shown per row does not mean "n
  contributing to every column" — a metric-specific effective n can be lower once
  nulls are excluded, and the UI/API give no per-metric n to disambiguate this.
- **Single-replicate ("group of one") rollup** — `HPHT_902` (no lettered
  siblings) returned exactly the documented shape:
  `{"n_replicates":1,"mean_h2_micromoles":25.45888617671324,"sd_h2_micromoles":null,...}`
  — mean equals the single value, `sd` is `null` rather than `0` or `NaN`, as
  documented in `MODELS.md`.
- **No console errors or failed/slow network requests** were observed at any point
  in this session (checked via the DevTools Console and Network panels across
  every page visited, plus after each write).

---

## Open questions / things I couldn't fully confirm

- Whether `time_post_reaction_bucket_days` is unset on **every** hand-entered
  result app-wide, or only exhibits under some subset of conditions — I only
  tested via the "Add Results" modal (the only UI path for creating a new
  timepoint), and the code (`create_result`) has no conditional logic around this
  field, so I'm confident it's unconditional, but I did not test every possible
  request-construction path (e.g. hitting `POST /api/results` directly with a
  fully custom payload that explicitly includes `time_post_reaction_bucket_days` —
  the schema would presumably accept a manually-supplied value, since nothing
  strips it, but the UI never sends one).
- The Postgres-vs-SQLite question in Finding #5 — I did not connect to the
  database directly to confirm which engine is actually live, so the `GREATEST()`
  NULL-semantics explanation is my best read of the SQL, not something I
  independently executed against the DB.
- I made one exploratory direct `fetch()` `POST /api/experiments` call from the
  browser console (bypassing the app's own request flow) using a copied Bearer
  token, and got `401 Invalid or expired token` even though the same token's `exp`
  claim was ~54 minutes in the future and was concurrently accepted by the backend
  for reads made through the actual app. Every write made *through* the real UI
  succeeded without issue throughout the session. I didn't investigate this
  further since it's not a UI/API-through-the-app problem and is outside scope,
  but it was unexpected enough to note.
