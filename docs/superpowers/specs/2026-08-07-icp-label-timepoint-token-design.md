# ICP label timepoint: `-t<days>` token wins over `_Day<n>`

**Date:** 2026-08-07
**Task mode:** inline
**Branch:** `fix/icp-label-timepoint-token` off `develop`
**Status:** design approved, awaiting spec review

---

## 1. Problem

The ICP-OES upload derives a result's timepoint from the `_Day<n>` token in the
instrument's `Label` column. Since issue #81, a destructively-sampled vial encodes
its own timepoint in its experiment ID as a trailing `-t<days>` token. The new
labelling convention carries both:

```
SERUM_Cation_005c-t5_Day12_21x
HPHT_231_Day6_21x
```

The ID is canonical for the vial's day. The ICP parser does not know that.

### 1.1 What actually breaks

The premise that the ID fails to parse is **false** — verified by running the
parser. `extract_sample_info`'s regex (`backend/services/icp_service.py:156`) is
anchored to the end of the label:

```
_(Day|Time)(\d+(?:\.\d+)?)_(\d+(?:\.\d+)?)x?$
```

It peels only `_Day12_21x`, leaving `-t5` attached to the ID, and
`_find_experiment` resolves that ID correctly. Measured behaviour:

| Label | → `experiment_id` | day from label | `-t` in ID |
|---|---|---|---|
| `SERUM_Cation_005c-t5_Day12_21x` | `SERUM_Cation_005c-t5` | **12.0** | **5.0** |
| `HPHT_231_Day6_21x` | `HPHT_231` | 6.0 | — |
| `SERUM_Catalyst_001a-t7_Day7_21x` | `SERUM_Catalyst_001a-t7` | 7.0 | 7.0 |
| `SERUM_Cation_005c-t5_21x` | — | **None — skipped silently** | — |
| `SERUM_Cation_005c-t0.5_Day0.5_21x` | `SERUM_Cation_005c-t0.5` | 0.5 | 0.5 |

Three real defects follow.

**D1 — silent wrong timepoint.** ICP writes the result at day 12 on a vial whose
ID declares day 5. `icp_service.py` never calls `apply_id_timepoint`
(`backend/services/result_merge_utils.py:21`), the guard that
`scalar_results_service.py:112` and `results.py:98` both use. ICP is the only
write path that can do this without raising. `_find_or_create_experimental_result`
then buckets on that wrong time, so the ICP data lands in a bucket no scalar row
will ever share, and `v_results_scalar_rollup` aggregates it at the wrong day.

**D2 — dropping `Day` is total silent data loss.** `extract_sample_info` returns
`None` and `process_icp_dataframe:356` executes a bare `continue` — no error, no
warning. A file whose labels omit `Day` reports "0 created" with no explanation.
Compounding it, `dilution_factor` is welded into the same regex as `Day`, so `21x`
cannot be found without restructuring the pattern.

**D3 — old-style labels can no longer resolve `-t` vials.** All 82 `-t` vial stems
in the dev DB have **zero** bare experiment rows, so `SERUM_Catalyst_001a_Day7_21x`
matches nothing. `auto_create_treatment_experiment` declines that ID shape, so it
errors per sample — visible, but every row fails. Fixed incidentally: labels
carrying the vial's real `-t` ID resolve, which is the convention going forward.

### 1.2 Production state — nothing is corrupted

Measured against the dev DB, 2026-08-07:

| Measurement | Value |
|---|---|
| `icp_results` rows | 969 |
| …whose `raw_label` carries a `-t` token | **0** |
| …whose `raw_label` carries a `_Day`/`_Time` token | 969 |
| `experiments` rows | 1009 |
| …with `id_timepoint_days` set (a `-t` vial) | 167 |
| distinct `-t` vial stems | 82 |
| …of those stems having a bare experiment row | **0** |
| ICP results attached to any `-t` vial | **0** |
| ICP results whose day disagrees with `id_timepoint_days` | **0** |

The failure is entirely prospective. **No data repair or backfill is in scope.**

---

## 2. Decisions taken

| # | Question | Decision |
|---|---|---|
| D-a | `Day` disagrees with `-t` | **`-t` wins**, unconditionally; the row is never rejected |
| D-b | Accepted label shapes | **`Day` optional when `-t` is present**; `Day` still supplies the day when there is no `-t` |
| D-c | Labels with no time source | **Reported as warnings**, not errors |
| D-d | Disagreement visibility | **One file-level warning**, aligning with `master_bulk_upload.py:766` |

D-a and D-d reproduce a contract already established in the sibling parser.
`master_bulk_upload.py:383-389` records the ruling verbatim:

> The `-t<days>` token defines the vial's elapsed days (Mat, 2026-07-30), so it
> wins outright — a disagreeing Duration is reported, not rejected. This
> deliberately differs from `POST /api/results`, which still 400s on a conflict
> via `apply_id_timepoint`: a hand-entered result has one author to correct,
> whereas the Duration column here is a formula derived from sampling dates, and
> letting it veto the ID would reject a whole sheet's readings over provenance
> the ID already settles.

The same reasoning transfers: an ICP label's `Day` value is written by the
worklist/naming convention, not by an author who can be asked to correct one row.
ICP therefore does **not** adopt `apply_id_timepoint`, whose contract is to raise.

D-c is the direct remedy for D2. Under D-b, a mistyped `-T5` (uppercase — see
§5.2) yields no time source, so without D-c the whole-file failure mode returns in
a new form.

---

## 3. Contract

Parse the label right-to-left:

1. **Dilution token `_<N>x`** — required. The trailing `x` stays optional, preserving
   today's `x?` leniency (`Serum_MH_011_Day5_5` parses with dilution 5).
2. **Optional `_Day<N>` / `_Time<N>`** — case-insensitive, as today.
3. **The remainder is the experiment ID**, handed to `split_timepoint_token`.

Time resolution:

| ID has `-t` | Label has `Day` | Effective day | Warning |
|---|---|---|---|
| yes | yes, agrees | `-t` value | — |
| yes | yes, disagrees | `-t` value | disagreement (file-level) |
| yes | no | `-t` value | — |
| no | yes | `Day` value | — |
| no | no | — row skipped | skip (file-level) |

Agreement is compared with `TIMEPOINT_TOLERANCE_DAYS` (0.0001), the same
tolerance `apply_id_timepoint` and `master_bulk_upload.py:394` use.

Worked examples:

```
ACCEPTED, time from -t:
  SERUM_Cation_005c-t5_21x         -> exp SERUM_Cation_005c-t5, day 5,   dil 21
  SERUM_Cation_005c-t5_Day12_21x   -> exp SERUM_Cation_005c-t5, day 5,   dil 21  (Day12 ignored, warned)
  SERUM_Cation_005c-t0.5_Day0.5_21x-> exp SERUM_Cation_005c-t0.5, day 0.5, dil 21 (agrees, silent)

ACCEPTED, time from Day (unchanged):
  HPHT_231_Day6_21x                -> exp HPHT_231,     day 6, dil 21
  Serum_MH_011_Day5_5x             -> exp Serum_MH_011, day 5, dil 5
  Serum-MH-025_Time3_10x           -> exp Serum-MH-025, day 3, dil 10

NO TIME SOURCE -> skipped, reported:
  HPHT_231_21x
  SERUM_Cation_005c-T5_21x         (uppercase T is not the canonical token)

SKIPPED, NOT reported (as today):
  Standard 1
  Blank
  HPHT_231
```

---

## 4. Implementation

Three layers. All parser work is in `backend/services/icp_service.py`; the router
change only populates response fields that already exist.

### 4.1 Parser — `_ex` helpers, existing entry points kept as wrappers

A trap forces this shape. `create_icp_result` splats `**sample_info` into
`result_data` (`icp_service.py:385`), then line 520 writes **every** key not
listed in `NON_ELEMENT_FIELDS` into the `all_elements` JSONB:

```python
elif key not in ICPService.NON_ELEMENT_FIELDS and value is not None:
    all_elements_data[key] = value      # <- any new key becomes a fake element
```

So diagnostics must not ride in the splatted dict. They travel in a dataclass,
and the dict keeps its exact three-key shape:

```python
@dataclass(frozen=True)
class LabelInfo:
    experiment_id: str
    time_post_reaction: float          # the EFFECTIVE day
    dilution_factor: float
    time_source: Literal['id_token', 'day_label']
    label_day_days: Optional[float]    # what Day said, even when unused
    day_disagrees: bool

extract_sample_info_ex(label) -> Optional[LabelInfo]   # new, full fidelity
extract_sample_info(label)    -> Optional[dict]        # unchanged 3-key contract
```

`extract_sample_info` becomes a thin wrapper over `extract_sample_info_ex`,
returning only `experiment_id` / `time_post_reaction` / `dilution_factor`. This
mirrors the codebase's existing `_ex` convention (`create_scalar_result_ex`,
`from_bytes_ex`) and keeps the tested public helper's contract intact.

Two regexes replace the single welded one, unsticking dilution from `Day` (D2):

```python
_DILUTION_RE = re.compile(r'_(\d+(?:\.\d+)?)x?$', re.IGNORECASE)
_DAY_RE      = re.compile(r'_(?:Day|Time)(\d+(?:\.\d+)?)$', re.IGNORECASE)
```

`-t` parsing **delegates to `database.experiment_id_parser.split_timepoint_token`**
and is never re-implemented. ICP therefore cannot drift from the canonical
grammar — which is exactly the `_t1`-vs-`-t1` divergence recorded in
`docs/working/issue-log.md` as needing its own task.

**Peeling order is load-bearing.** Dilution comes off first so that `-t5` is at
end-of-string when `split_timepoint_token` (anchored with `$`) runs.
`_DILUTION_RE` cannot mis-fire on a `-t` token: it requires `_` immediately before
the digits, and in `...-t5` the preceding character is `t`.

### 4.2 Aggregation — `process_icp_dataframe_ex`

Returns `(processed_data, errors, warnings, skipped_count)`;
`process_icp_dataframe` stays a 2-tuple wrapper. Likewise
`parse_and_process_icp_file_ex` alongside the existing
`parse_and_process_icp_file`.

Per-label counters accumulate; two file-level lines are emitted at the end.

**Disagreement warning** — mirrors `master_bulk_upload.py:766-780`, including its
≤10 list cap, and stays one line per file rather than one per row:

```
Day token disagrees with the ID's -t token on {n} of {comparable} label(s)
({labels}). The ID is canonical, so each reading was recorded at the day its ID
encodes and the Day value was not used.
```

`{comparable}` counts labels where **both** a `-t` token and a `Day`/`Time` token
were present — the only labels where a comparison was possible. Labels with just
one of the two are in neither the numerator nor the denominator.

**Skip warning:**

```
{n} label(s) were skipped because no timepoint could be determined ({labels}) —
no '-t<days>' token in the ID and no Day/Time token in the label. Note the
timepoint token is lowercase '-t' only.
```

A skip is reported only when the label carries at least one of: a `_<N>x`
dilution token **with** the `x`, a `Day`/`Time` token, or a `-[tT]<digit>`
sequence. `Standard 1` and `Blank` match none and stay silent, as designed; a
bare `HPHT_231` also stays silent, avoiding a false positive from `_DILUTION_RE`
matching its trailing `_231`.

Note the deliberate asymmetry: **parsing** accepts a dilution token without the
trailing `x` (§3, preserving today's leniency), but **skip-reporting** requires
the `x`. So `HPHT_231_5` — indistinguishable from a bare ID with a numeric
segment — is skipped silently, while `HPHT_231_21x` is reported. The stricter
test applies only to deciding whether a skip is worth a researcher's attention;
it never affects whether a label parses.

Known acceptable false positive: a QC standard labelled with an `x` dilution
(e.g. `QC_Std_5x`) is reported as a skip. It is a warning that names the label, so
a researcher can see what it is. Widening the existing `Type != 'BLK'` filter to
also drop `STD`/`CAL` rows is **out of scope**.

The `uncal_warnings` from `select_best_lines` currently land in `errors`
(`icp_service.py:370`). They stay there — moving them is out of scope and would
change existing behaviour unrelated to this task.

### 4.3 Router

`backend/api/routers/bulk_uploads.py:459-463` already has both fields available:
`UploadResponse` declares `warnings: list[str] = []` and `skipped: int`
(`backend/api/schemas/bulk_upload.py:95-98`), but the ICP endpoint passes no
warnings and hardcodes `skipped=0`. It switches to
`parse_and_process_icp_file_ex` and passes both through.

No schema change. No frontend change — the bulk-upload panel already renders
`warnings`.

The existing gate at line 444 (`if parse_errors and not processed_data`) keeps its
condition — warnings never block an upload — but **its early `return` must also
pass `warnings=`**. This is the case that matters most: when every label in a file
is skipped, `processed_data` is empty, `validate_icp_data` contributes "No data to
validate", the gate fires, and the function returns at line 445. As written that
branch constructs `UploadResponse` without `warnings`, so the skip explanation —
the only thing telling the researcher *why* nothing uploaded — would be dropped
precisely on a whole-file labelling mistake, which is D2 surviving the fix. Both
`return` sites pass warnings.

---

## 5. Out of scope

### 5.1 `_find_experiment`'s divergent normalization

`icp_service.py:769` normalizes with its own naive lowercase strip-and-concatenate
key and resolves with `.first()`, rather than the canonical
`_id_match.normalize_id` / `find_experiment_matches`. Consequences: it is
*stricter* on zero padding than the canonical key
(`SERUM_Catalyst_1a-t7` will not match `SERUM_Catalyst_001a-t7`) and it picks
arbitrarily when two experiments collide.

Measured 0 collisions across all 1009 current experiments (2026-08-07), and
re-keying an experiment lookup is the same class of change that required its own
sign-off for `master_bulk_upload.py` earlier the same day. Follow-up task.

### 5.2 `-T5` and `_t5` spellings

`split_timepoint_token` accepts lowercase `-t` only, by documented deliberate
choice, while `_id_match.normalize_id` treats `_t1` and `-t1` as the same key.
`docs/working/issue-log.md` already ruled this needs its own `/start-task`: "it
changes the canonical ID grammar used by lineage repo-wide, not just this parser."

This spec does not touch that grammar. It only ensures such a label lands in the
*reported* skip bucket (D-c) instead of vanishing.

### 5.3 Data repair

None required — see §1.2.

### 5.4 Stored provenance

Neither the discarded `Day` value nor `time_source` is persisted. Doing so would
be an additive `ICPResults` column and a schema-checklist run. The file-level
warning is the only record, consistent with how `h2_source` is handled for
Master Results.

---

## 6. Tests

Tests go in **`tests/test_icp_handling.py`**, the real suite (1144 lines, 176
asserts, pytest classes with a SQLite in-memory `test_db` fixture).

Corrected 2026-08-07: an earlier draft of this section named
`tests/test_icp_parsing.py`. That file is a print-only script — it re-implements
`extract_sample_info` locally, asserts nothing, and never imports
`backend.services.icp_service`. It is worthless as a regression harness and is
left untouched. `tests/test_icp_service.py` is likewise `main()`-shaped with only
5 asserts.

A useful consequence: `TestICPServiceBasicFunctionality::test_extract_sample_info_valid_labels`
(`tests/test_icp_handling.py:118-120`) already asserts **exact dict equality**
against the three keys, so the §4.1 `all_elements` trap is *already* guarded by an
existing test — adding a key to the returned dict breaks it. All 7 labels in
`test_extract_sample_info_invalid_labels` still return `None` under the new
grammar (verified by hand, including `Standard_1`, whose trailing `_1` does match
`_DILUTION_RE` but which then has no timepoint source).

New cases:

| Case | Expectation |
|---|---|
| `SERUM_Cation_005c-t5_Day12_21x` | day 5, dil 21, `time_source='id_token'`, `day_disagrees=True`, `label_day_days=12.0` |
| `SERUM_Cation_005c-t5_21x` | day 5, dil 21, `time_source='id_token'`, `day_disagrees=False`, `label_day_days=None` |
| `SERUM_Cation_005c-t0.5_Day0.5_21x` | day 0.5, `day_disagrees=False` (tolerance) |
| `SERUM_Catalyst_001a-t7_Day7_21x` | day 7, agrees, silent |
| `HPHT_231_Day6_21x` | **regression** — day 6, dil 21, `time_source='day_label'` |
| `Serum_MH_011_Day5_5x` | **regression** — the doc's own example, unchanged |
| `Serum-MH-025_Time3_10x` | **regression** — `Time` spelling, unchanged |
| `Serum_MH_011_Day5_5` | **regression** — optional `x`, dil 5 |
| `HPHT_231_21x` | `None`, **and** counted as a reported skip |
| `SERUM_Cation_005c-T5_21x` | `None`, **and** counted as a reported skip |
| `Standard 1`, `Blank`, `HPHT_231` | `None`, **not** reported |
| `extract_sample_info` (non-`_ex`) | returns exactly `{experiment_id, time_post_reaction, dilution_factor}` — guards the §4.1 `all_elements` trap (already covered by the existing exact-equality test) |

Aggregation tests on `process_icp_dataframe_ex`: one disagreement warning per
file (not per row); the ≤10 label-list cap; the skip count reaching
`skipped_count`.

One service-level test: seed a `-t5` vial, upload a `..._Day12_21x` label, assert
the `ICPResults` row hangs off the `ExperimentalResults` whose
`time_post_reaction_days` is 5.0, and that exactly one disagreement warning is
returned. Per `docs/working/` precedent, seed and roll back rather than relying on
dev-DB contents.

Existing suites that must stay green: `tests/test_icp_handling.py` (in particular
`test_extract_sample_info_valid_labels`, `test_extract_sample_info_invalid_labels`
and `test_process_icp_dataframe_success`, whose 2-tuple unpack is why
`process_icp_dataframe` keeps its arity), `tests/api/test_bulk_uploads.py`, and
`tests/test_time_field_guardrails.py`.

---

## 7. Docs and locks

| File | Change |
|---|---|
| `docs/upload_templates/icp_oes_upload.md:26-31` | replace the single-pattern grammar with §3's table and examples |
| `docs/LOCKED_COMPONENTS.md:52` | numbered footnote ³ on the `icp_service.py` row, recording the changed contract and this sign-off — the convention set by ¹ (issue #86) and ² (the duplicate guard) |
| `MODELS.md` | the `id_timepoint_days` bullet names only the scalar/master parsers as enforcing the ID's canonical day; add the ICP label path, noting it warns rather than rejects |
| `docs/working/issue-log.md` | entry at completion |

`icp_service.py` is a **locked** parser (`docs/LOCKED_COMPONENTS.md:52`, listed in
the Bulk Upload Python Parsers table despite living in `backend/services/`).
Explicit sign-off given by Mat, 2026-08-07.

---

## 8. Acceptance criteria

- [ ] `SERUM_Cation_005c-t5_Day12_21x` writes its ICP row at day **5**, not 12
- [ ] `SERUM_Cation_005c-t5_21x` (no `Day`) parses and writes at day 5
- [ ] `HPHT_231_Day6_21x` and `Serum_MH_011_Day5_5x` behave exactly as before
- [ ] A `Day`/`-t` disagreement produces exactly **one** file-level warning, capped at 10 named labels, and rejects **no** row
- [ ] A label with no time source is skipped, counted in `skipped`, and named in a warning
- [ ] `Standard 1` / `Blank` remain silently skipped
- [ ] `extract_sample_info` still returns exactly three keys, so no diagnostic key can reach `all_elements`
- [ ] `warnings` and a real `skipped` reach `UploadResponse` with no schema or frontend change
- [ ] A file whose every label is skipped still returns its skip warning — the early-return branch at `bulk_uploads.py:445` passes `warnings=`
- [ ] All five existing suites in §6 pass
- [ ] Footnote ³ added to `docs/LOCKED_COMPONENTS.md`
