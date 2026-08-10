# ICP Label Timepoint Token Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the ICP-OES upload take a vial's timepoint from the experiment ID's canonical `-t<days>` token instead of the label's `_Day<n>` token, reporting disagreements and unparseable labels instead of silently mis-filing or dropping them.

**Architecture:** All parsing changes are confined to `backend/services/icp_service.py`. New `_ex` variants carry full-fidelity results (a frozen `LabelInfo` dataclass plus warnings and a skip count); the three existing entry points become thin wrappers that keep their current arity and key sets, so every existing test stays green. The router only populates two `UploadResponse` fields that already exist. The `-t` grammar itself is never re-implemented — it delegates to `database.experiment_id_parser.split_timepoint_token`.

**Tech Stack:** Python 3, pandas, SQLAlchemy, FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-08-07-icp-label-timepoint-token-design.md`

## Global Constraints

- **`backend/services/icp_service.py` is a LOCKED parser** (`docs/LOCKED_COMPONENTS.md:52`). Sign-off given by Mat, 2026-08-07. Task 5 adds the required footnote ³.
- **Branch:** `fix/icp-label-timepoint-token` (already created off `develop`). Do not create another.
- **Commit format** (`.claude/CLAUDE.md` §8), inline mode: `[fix] <imperative, <50 chars, no trailing period>` followed by a body with `- Tests added: yes/no` and `- Docs updated: yes/no`.
- **Never change `database/models/`.** No schema change, no migration, no new dependency.
- **Do not re-implement the `-t<days>` grammar.** Always call `split_timepoint_token`.
- **`extract_sample_info` must keep returning exactly three keys** — `experiment_id`, `time_post_reaction`, `dilution_factor`. `create_icp_result` splats it into `result_data` and `icp_service.py:520` writes every key not in `NON_ELEMENT_FIELDS` into the `all_elements` JSONB, so a fourth key becomes a fake element.
- **`process_icp_dataframe` and `parse_and_process_icp_file` must keep returning 2-tuples.** Existing tests unpack exactly two values.
- **Timepoint comparisons use `TIMEPOINT_TOLERANCE_DAYS`** (0.0001) from `backend/services/result_merge_utils.py`. Never a bare `==` on floats.
- **Warnings never block an upload.** They go in `warnings`, never `errors`.
- **Do not touch `_find_experiment`** (`icp_service.py:757-786`) — explicitly out of scope (spec §5.1).
- **Do not touch `tests/test_icp_parsing.py` or `tests/test_icp_service.py`** — print-only scripts, not real harnesses (spec §6).
- **Run pytest one process at a time.** The Postgres test DB is shared; two concurrent runs corrupt it.

**Test command prefix:** the venv is not on PATH. Use `.venv/Scripts/python -m pytest`.

---

### Task 1: Label parser — `LabelInfo` and `extract_sample_info_ex`

**Files:**
- Modify: `backend/services/icp_service.py` (imports at 1-16; replace `extract_sample_info` at 135-188)
- Test: `tests/test_icp_handling.py` (append a new class after `TestICPServiceBasicFunctionality`, which ends at line 176)

**Interfaces:**
- Consumes: `split_timepoint_token` from `database.experiment_id_parser`; `TIMEPOINT_TOLERANCE_DAYS` from `backend.services.result_merge_utils`.
- Produces:
  - `ICPService.extract_sample_info_ex(label: str) -> Optional[LabelInfo]`
  - `LabelInfo` frozen dataclass with fields `experiment_id: str`, `time_post_reaction: float`, `dilution_factor: float`, `time_source: Literal['id_token', 'day_label']`, `label_day_days: Optional[float]`, `day_disagrees: bool`
  - `ICPService.extract_sample_info(label: str) -> Optional[Dict[str, Any]]` — unchanged 3-key contract
  - Module-level `_DILUTION_RE`, `_DAY_RE`, `_LOOKS_LIKE_SAMPLE_RE` (Task 2 uses `_LOOKS_LIKE_SAMPLE_RE`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_icp_handling.py`:

```python
class TestICPLabelTimepointToken:
    """The ID's '-t<days>' token is canonical for a vial's day (spec 2026-08-07)."""

    def test_id_token_wins_over_disagreeing_day(self):
        info = ICPService.extract_sample_info_ex("SERUM_Cation_005c-t5_Day12_21x")
        assert info is not None
        assert info.experiment_id == "SERUM_Cation_005c-t5"
        assert info.time_post_reaction == 5.0
        assert info.dilution_factor == 21.0
        assert info.time_source == "id_token"
        assert info.label_day_days == 12.0
        assert info.day_disagrees is True

    def test_day_token_may_be_omitted_entirely(self):
        info = ICPService.extract_sample_info_ex("SERUM_Cation_005c-t5_21x")
        assert info is not None
        assert info.experiment_id == "SERUM_Cation_005c-t5"
        assert info.time_post_reaction == 5.0
        assert info.dilution_factor == 21.0
        assert info.time_source == "id_token"
        assert info.label_day_days is None
        assert info.day_disagrees is False

    def test_agreeing_day_is_not_a_disagreement(self):
        info = ICPService.extract_sample_info_ex("SERUM_Catalyst_001a-t7_Day7_21x")
        assert info is not None
        assert info.time_post_reaction == 7.0
        assert info.day_disagrees is False

    def test_fractional_token_agrees_within_tolerance(self):
        info = ICPService.extract_sample_info_ex("SERUM_Cation_005c-t0.5_Day0.5_21x")
        assert info is not None
        assert info.experiment_id == "SERUM_Cation_005c-t0.5"
        assert info.time_post_reaction == 0.5
        assert info.day_disagrees is False

    def test_day_still_supplies_time_when_id_has_no_token(self):
        info = ICPService.extract_sample_info_ex("HPHT_231_Day6_21x")
        assert info is not None
        assert info.experiment_id == "HPHT_231"
        assert info.time_post_reaction == 6.0
        assert info.dilution_factor == 21.0
        assert info.time_source == "day_label"
        assert info.label_day_days == 6.0
        assert info.day_disagrees is False

    @pytest.mark.parametrize("label,exp_id,day,dil", [
        ("Serum_MH_011_Day5_5x", "Serum_MH_011", 5.0, 5.0),
        ("Serum-MH-025_Time3_10x", "Serum-MH-025", 3.0, 10.0),
        ("Serum_MH_011_Day5_5", "Serum_MH_011", 5.0, 5.0),   # trailing 'x' optional
        ("HPHT_MH_004_Day7.5_15x", "HPHT_MH_004", 7.5, 15.0),
    ])
    def test_legacy_labels_are_unchanged(self, label, exp_id, day, dil):
        info = ICPService.extract_sample_info_ex(label)
        assert info is not None
        assert info.experiment_id == exp_id
        assert info.time_post_reaction == day
        assert info.dilution_factor == dil
        assert info.time_source == "day_label"

    @pytest.mark.parametrize("label", [
        "HPHT_231_21x",                 # dilution but no timepoint anywhere
        "SERUM_Cation_005c-T5_21x",     # uppercase T is not the canonical token
        "SERUM_Cation_005c_t5_21x",     # underscore spelling is not the canonical token
        "Standard 1",
        "Blank",
        "Standard_1",
        "HPHT_231",
        "",
    ])
    def test_labels_with_no_timepoint_return_none(self, label):
        assert ICPService.extract_sample_info_ex(label) is None

    def test_wrapper_returns_exactly_three_keys(self):
        """Guards the all_elements trap: create_icp_result splats this dict and
        icp_service.py:520 stores any unknown key as a fake element."""
        result = ICPService.extract_sample_info("SERUM_Cation_005c-t5_Day12_21x")
        assert set(result.keys()) == {
            "experiment_id", "time_post_reaction", "dilution_factor"
        }
        assert result["time_post_reaction"] == 5.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_icp_handling.py::TestICPLabelTimepointToken -v`

Expected: every test FAILS with `AttributeError: type object 'ICPService' has no attribute 'extract_sample_info_ex'`.

- [ ] **Step 3: Add the imports and module-level regexes**

In `backend/services/icp_service.py`, change the import block at lines 1-16. Add `dataclass`, `Literal`, `split_timepoint_token`, and `TIMEPOINT_TOLERANCE_DAYS`:

```python
import pandas as pd
import re
import datetime as dt
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Literal, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import Experiment, ExperimentalResults, ICPResults, ModificationsLog
from database.experiment_id_parser import split_timepoint_token
from io import StringIO
from frontend.config.variable_config import ICP_FIXED_ELEMENT_FIELDS
from backend.services.result_merge_utils import (
    TIMEPOINT_TOLERANCE_DAYS,
    create_experimental_result_row,
    ensure_primary_result_for_timepoint,
    find_timepoint_candidates,
    choose_parent_candidate,
    update_cumulative_times_for_chain,
)
```

Then insert immediately after that import block, before `class ICPService`:

```python
# Label grammar, peeled right-to-left (spec 2026-08-07 §3). Dilution is split out
# of the old welded '_(Day|Time)N_Nx$' pattern so that a label MAY omit Day: the
# ID's '-t<days>' token supplies the day instead.
_DILUTION_RE = re.compile(r'_(\d+(?:\.\d+)?)x?$', re.IGNORECASE)
_DAY_RE = re.compile(r'_(?:Day|Time)(\d+(?:\.\d+)?)$', re.IGNORECASE)

# Whether an unparseable label is worth telling the researcher about. Standards
# and blanks ("Standard 1", "Blank", "Standard_1") match none of these and stay
# silently skipped, as they always have. A bare ID ("HPHT_231") also stays silent
# even though _DILUTION_RE matches its trailing '_231' — the required 'x' is what
# distinguishes a real dilution token from an ID's numeric segment here. This
# stricter test governs REPORTING only; it never affects whether a label parses.
_LOOKS_LIKE_SAMPLE_RE = re.compile(r'_\d+(?:\.\d+)?x$|_(?:Day|Time)\d|-[tT]\d')


@dataclass(frozen=True)
class LabelInfo:
    """Everything an ICP `Label` encodes, including provenance that is discarded.

    `time_post_reaction` is the EFFECTIVE day. `label_day_days` retains what the
    label's Day/Time token said even when it was not used, so the caller can
    report a disagreement without re-parsing.
    """
    experiment_id: str
    time_post_reaction: float
    dilution_factor: float
    time_source: Literal['id_token', 'day_label']
    label_day_days: Optional[float]
    day_disagrees: bool
```

- [ ] **Step 4: Replace `extract_sample_info` with `extract_sample_info_ex` plus a wrapper**

Replace the whole of `extract_sample_info` (`backend/services/icp_service.py:135-188`, from the `@staticmethod` decorator through the `return None` of its `except` block) with:

```python
    @staticmethod
    def extract_sample_info_ex(label: str) -> Optional[LabelInfo]:
        """
        Parse an ICP `Label` into experiment ID, effective timepoint and dilution.

        Grammar, peeled right-to-left:
          1. `_<N>x` dilution token (required; the trailing 'x' is optional)
          2. optional `_Day<N>` / `_Time<N>` token
          3. whatever remains is the experiment ID

        The experiment ID's trailing '-t<days>' token is canonical for that vial's
        day (Mat, 2026-07-30), so when present it WINS outright and the label's Day
        value is discarded — reported by the caller, never rejected. This matches
        `master_bulk_upload.py:383` and deliberately differs from
        `POST /api/results`, which still 400s on a conflict via `apply_id_timepoint`:
        a hand-entered result has one author to correct, whereas an ICP label is
        machine-written by the worklist.

        Returns None when no timepoint can be determined — no '-t' token in the ID
        and no Day/Time token in the label — or when there is no dilution token.
        Standards and blanks ("Standard 1", "Blank") fall out here.

        Examples:
            'SERUM_Cation_005c-t5_Day12_21x' -> day 5.0,  day_disagrees=True
            'SERUM_Cation_005c-t5_21x'       -> day 5.0,  label_day_days=None
            'HPHT_231_Day6_21x'              -> day 6.0,  time_source='day_label'
            'HPHT_231_21x'                   -> None
        """
        if not label or not isinstance(label, str):
            return None

        remainder = label.strip()

        dilution_match = _DILUTION_RE.search(remainder)
        if not dilution_match:
            return None
        dilution_factor = float(dilution_match.group(1))
        remainder = remainder[:dilution_match.start()]

        label_day_days: Optional[float] = None
        day_match = _DAY_RE.search(remainder)
        if day_match:
            label_day_days = float(day_match.group(1))
            remainder = remainder[:day_match.start()]

        experiment_id = remainder.rstrip('_-')
        if not experiment_id:
            return None

        # Never re-implement the token grammar here: delegate to the canonical
        # parser so ICP cannot drift from lineage. The '_t5' / '-T5' spellings are
        # deliberately NOT accepted -- widening them changes the repo-wide ID
        # grammar and has its own task (docs/working/issue-log.md, 2026-08-07).
        _stem, id_timepoint_days = split_timepoint_token(experiment_id)

        if id_timepoint_days is not None:
            disagrees = (
                label_day_days is not None
                and abs(label_day_days - id_timepoint_days) > TIMEPOINT_TOLERANCE_DAYS
            )
            return LabelInfo(
                experiment_id=experiment_id,
                time_post_reaction=id_timepoint_days,
                dilution_factor=dilution_factor,
                time_source='id_token',
                label_day_days=label_day_days,
                day_disagrees=disagrees,
            )

        if label_day_days is None:
            return None

        return LabelInfo(
            experiment_id=experiment_id,
            time_post_reaction=label_day_days,
            dilution_factor=dilution_factor,
            time_source='day_label',
            label_day_days=label_day_days,
            day_disagrees=False,
        )

    @staticmethod
    def extract_sample_info(label: str) -> Optional[Dict[str, Any]]:
        """
        Backward-compatible three-key view of `extract_sample_info_ex`.

        The key set is deliberately FROZEN at experiment_id / time_post_reaction /
        dilution_factor. `create_icp_result` splats this dict into `result_data`
        and then stores every key not listed in `NON_ELEMENT_FIELDS` into the
        `all_elements` JSONB, so a fourth key here would be persisted as a fake
        element. Diagnostics live on `LabelInfo` instead.
        """
        info = ICPService.extract_sample_info_ex(label)
        if info is None:
            return None
        return {
            'experiment_id': info.experiment_id,
            'time_post_reaction': info.time_post_reaction,
            'dilution_factor': info.dilution_factor,
        }
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_icp_handling.py::TestICPLabelTimepointToken -v`

Expected: PASS (8 test functions, 12 parametrized cases).

- [ ] **Step 6: Run the whole existing ICP suite for regressions**

Run: `.venv/Scripts/python -m pytest tests/test_icp_handling.py -v`

Expected: PASS. Pay attention to three that specifically pin the old contract:
- `test_extract_sample_info_valid_labels` — exact 3-key dict equality
- `test_extract_sample_info_invalid_labels` — all 7 labels still `None`
- `test_process_icp_dataframe_success` — still unpacks a 2-tuple, `len(errors) == 0`

If any fail, STOP and report rather than loosening the assertion — these are the contract.

- [ ] **Step 7: Commit**

```bash
git add backend/services/icp_service.py tests/test_icp_handling.py
git commit -m "$(cat <<'EOF'
[fix] Take the ICP label timepoint from the ID

- extract_sample_info_ex returns LabelInfo; the '-t<days>' ID token
  wins over the label's _Day<n>, which is retained for reporting
- Dilution is unwelded from Day so a label may omit Day entirely
- extract_sample_info stays a frozen 3-key wrapper (all_elements trap)
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Aggregate the file-level warnings

**Files:**
- Modify: `backend/services/icp_service.py` (`process_icp_dataframe` at 304-400; `parse_and_process_icp_file` at 915-954)
- Test: `tests/test_icp_handling.py` (append to `TestICPLabelTimepointToken`)

**Interfaces:**
- Consumes: `ICPService.extract_sample_info_ex`, `LabelInfo`, `_LOOKS_LIKE_SAMPLE_RE` (Task 1).
- Produces:
  - `ICPService.process_icp_dataframe_ex(df) -> Tuple[List[Dict[str, Any]], List[str], List[str], int]` returning `(processed_data, errors, warnings, skipped_count)`
  - `ICPService.parse_and_process_icp_file_ex(file_content, manual_header_row=0) -> Tuple[List[Dict[str, Any]], List[str], List[str], int]` — same 4-tuple
  - `process_icp_dataframe` and `parse_and_process_icp_file` keep their 2-tuple signatures as wrappers over the above

- [ ] **Step 1: Write the failing tests**

Append these methods to `class TestICPLabelTimepointToken` in `tests/test_icp_handling.py`:

```python
    @staticmethod
    def _csv(labels):
        """Minimal 2-header-row ICP export with one Fe row per label."""
        rows = "\n".join(
            f"{label},Fe 238.204,10.0,1500,SAMP" for label in labels
        )
        return (
            "Header Row 1\nHeader Row 2\n"
            "Label,Element Label,Concentration,Intensity,Type\n"
            f"{rows}\n"
        ).encode("utf-8")

    def test_disagreement_emits_one_file_level_warning(self):
        df = ICPService.parse_csv_file(self._csv([
            "SERUM_Cation_005c-t5_Day12_21x",
            "SERUM_Cation_005d-t5_Day12_21x",
            "SERUM_Catalyst_001a-t7_Day7_21x",   # agrees: comparable, not counted
        ]))
        data, errors, warnings, skipped = ICPService.process_icp_dataframe_ex(df)

        assert len(data) == 3
        assert skipped == 0
        assert len(warnings) == 1
        w = warnings[0]
        assert "2 of 3 labels" in w
        assert "SERUM_Cation_005c-t5_Day12_21x" in w
        assert "SERUM_Cation_005d-t5_Day12_21x" in w
        assert "SERUM_Catalyst_001a-t7_Day7_21x" not in w
        # every row still written, at the ID's day
        assert sorted(d["time_post_reaction"] for d in data) == [5.0, 5.0, 7.0]

    def test_disagreement_warning_omits_label_list_above_ten(self):
        labels = [f"SERUM_Cation_{i:03d}a-t5_Day12_21x" for i in range(11)]
        df = ICPService.parse_csv_file(self._csv(labels))
        _data, _errors, warnings, _skipped = ICPService.process_icp_dataframe_ex(df)

        assert len(warnings) == 1
        assert "11 of 11 labels" in warnings[0]
        assert "SERUM_Cation_000a-t5_Day12_21x" not in warnings[0]

    def test_labels_with_no_timepoint_are_counted_and_named(self):
        df = ICPService.parse_csv_file(self._csv([
            "HPHT_231_Day6_21x",              # fine
            "HPHT_232_21x",                   # no timepoint -> reported
            "SERUM_Cation_005c-T5_21x",       # typo'd token -> reported
        ]))
        data, _errors, warnings, skipped = ICPService.process_icp_dataframe_ex(df)

        assert len(data) == 1
        assert skipped == 2
        assert len(warnings) == 1
        assert "HPHT_232_21x" in warnings[0]
        assert "SERUM_Cation_005c-T5_21x" in warnings[0]
        assert "lowercase" in warnings[0]

    def test_standards_and_blanks_are_never_reported(self):
        df = ICPService.parse_csv_file(self._csv([
            "HPHT_231_Day6_21x", "Standard 1", "Standard_1", "HPHT_231",
        ]))
        data, _errors, warnings, skipped = ICPService.process_icp_dataframe_ex(df)

        assert len(data) == 1
        assert skipped == 0
        assert warnings == []

    def test_clean_file_emits_no_warnings(self):
        df = ICPService.parse_csv_file(self._csv([
            "SERUM_Cation_005c-t5_21x", "HPHT_231_Day6_21x",
        ]))
        data, errors, warnings, skipped = ICPService.process_icp_dataframe_ex(df)

        assert len(data) == 2
        assert errors == []
        assert warnings == []
        assert skipped == 0

    def test_parse_and_process_ex_threads_warnings_through(self):
        content = self._csv(["SERUM_Cation_005c-t5_Day12_21x"])
        data, _errors, warnings, skipped = ICPService.parse_and_process_icp_file_ex(content)

        assert len(data) == 1
        assert data[0]["time_post_reaction"] == 5.0
        assert len(warnings) == 1
        assert skipped == 0

    def test_two_tuple_wrappers_keep_their_arity(self):
        content = self._csv(["SERUM_Cation_005c-t5_Day12_21x"])
        df = ICPService.parse_csv_file(content)

        data, errors = ICPService.process_icp_dataframe(df)
        assert len(data) == 1 and errors == []

        data2, errors2 = ICPService.parse_and_process_icp_file(content)
        assert len(data2) == 1 and errors2 == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_icp_handling.py::TestICPLabelTimepointToken -v -k "warning or timepoint_are or standards or clean_file or threads or arity"`

Expected: FAIL with `AttributeError: type object 'ICPService' has no attribute 'process_icp_dataframe_ex'`.

- [ ] **Step 3: Rename `process_icp_dataframe` to `_ex` and add the counters**

In `backend/services/icp_service.py`, change the signature and docstring return line of the method currently at line 304:

```python
    @staticmethod
    def process_icp_dataframe_ex(
        df: pd.DataFrame,
    ) -> Tuple[List[Dict[str, Any]], List[str], List[str], int]:
```

and its `Returns:` docstring line to:

```
        Returns:
            Tuple of (processed_data_list, error_messages, warnings, skipped_count).
            `warnings` holds at most two file-level lines: one for Day-vs-'-t'
            disagreements and one naming labels skipped for having no timepoint.
```

Immediately after `errors = []` (line 323), add the counters:

```python
        warnings: List[str] = []
        disagreement_labels: List[str] = []
        skipped_labels: List[str] = []
        comparable_labels = 0
```

Change the three early `return` statements in this method to 4-tuples:
- line 327 (`DataFrame is empty`): `return processed_data, errors, warnings, 0`
- line 334 (missing required columns): `return processed_data, errors, warnings, 0`
- line 345 (`No non-blank samples found`): `return processed_data, errors, warnings, 0`

Replace the label-handling block (lines 352-357 — from `# Extract sample information` through the `continue`) with:

```python
                    info = ICPService.extract_sample_info_ex(label)

                    # Skip standards, blanks and anything with no timepoint. A
                    # label that LOOKS like a sample is named in a warning so a
                    # whole-file labelling mistake is diagnosable instead of
                    # reporting "0 created" with no reason.
                    if info is None:
                        if _LOOKS_LIKE_SAMPLE_RE.search(str(label)):
                            skipped_labels.append(str(label))
                        continue

                    if info.time_source == 'id_token' and info.label_day_days is not None:
                        comparable_labels += 1
                        if info.day_disagrees:
                            disagreement_labels.append(str(label))

                    sample_info = {
                        'experiment_id': info.experiment_id,
                        'time_post_reaction': info.time_post_reaction,
                        'dilution_factor': info.dilution_factor,
                    }
```

Finally, replace the method's closing `return processed_data, errors` (line 400) with the warning assembly plus a 4-tuple return:

```python
        # One line per file, not one per row -- mirrors master_bulk_upload.py:755-780,
        # including its <=10 list cap. The ID wins either way so no row is
        # rejected, which is exactly why this must stay visible without drowning
        # the other warnings.
        if disagreement_labels:
            n = len(disagreement_labels)
            noun = "label" if comparable_labels == 1 else "labels"
            where = (
                " (" + ", ".join(disagreement_labels) + ")" if n <= 10 else ""
            )
            warnings.append(
                f"Day token disagrees with the ID's -t token on {n} of "
                f"{comparable_labels} {noun}{where}. The ID is canonical, so each "
                "reading was recorded at the day its ID encodes and the Day value "
                "was not used."
            )

        if skipped_labels:
            n = len(skipped_labels)
            noun = "label" if n == 1 else "labels"
            where = (
                " (" + ", ".join(skipped_labels) + ")" if n <= 10 else ""
            )
            warnings.append(
                f"{n} {noun} skipped -- no timepoint could be determined{where}. "
                "Neither a '-t<days>' token in the experiment ID nor a Day/Time "
                "token in the label was found. Note the timepoint token is "
                "lowercase '-t' only."
            )

        return processed_data, errors, warnings, len(skipped_labels)
```

- [ ] **Step 4: Add the `process_icp_dataframe` wrapper**

Insert immediately after `process_icp_dataframe_ex`, before `_standardize_element_name`:

```python
    @staticmethod
    def process_icp_dataframe(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Two-tuple view of `process_icp_dataframe_ex`, dropping warnings.

        Arity is frozen: existing callers and tests unpack exactly two values.
        """
        processed_data, errors, _warnings, _skipped = ICPService.process_icp_dataframe_ex(df)
        return processed_data, errors
```

- [ ] **Step 5: Add `parse_and_process_icp_file_ex` and reduce the original to a wrapper**

Replace the body of `parse_and_process_icp_file` (`backend/services/icp_service.py:915-954`) with both of these:

```python
    @staticmethod
    def parse_and_process_icp_file_ex(
        file_content: bytes,
        manual_header_row: int = 0,
    ) -> Tuple[List[Dict[str, Any]], List[str], List[str], int]:
        """
        Complete parse+process workflow, retaining file-level warnings.

        Returns:
            Tuple of (processed_data, errors, warnings, skipped_count).
        """
        try:
            df = ICPService.parse_csv_file(file_content, manual_header_row)

            if df.empty:
                return [], ["Parsed CSV file is empty"], [], 0

            processed_data, processing_errors, warnings, skipped = (
                ICPService.process_icp_dataframe_ex(df)
            )
            validation_errors = ICPService.validate_icp_data(processed_data)

            return processed_data, processing_errors + validation_errors, warnings, skipped

        except Exception as e:
            return [], [f"Error in ICP file processing workflow: {str(e)}"], [], 0

    @staticmethod
    def parse_and_process_icp_file(
        file_content: bytes,
        manual_header_row: int = 0,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Two-tuple view of `parse_and_process_icp_file_ex`, dropping warnings.

        Arity is frozen: existing callers and tests unpack exactly two values.
        """
        processed_data, errors, _warnings, _skipped = (
            ICPService.parse_and_process_icp_file_ex(file_content, manual_header_row)
        )
        return processed_data, errors
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_icp_handling.py::TestICPLabelTimepointToken -v`

Expected: PASS.

- [ ] **Step 7: Run the full ICP suite for regressions**

Run: `.venv/Scripts/python -m pytest tests/test_icp_handling.py -v`

Expected: PASS, including `test_process_icp_dataframe_success` and `test_parse_and_process_icp_file_complete_workflow`, which both unpack 2-tuples.

- [ ] **Step 8: Commit**

```bash
git add backend/services/icp_service.py tests/test_icp_handling.py
git commit -m "$(cat <<'EOF'
[fix] Report ICP label timepoint problems per file

- process_icp_dataframe_ex / parse_and_process_icp_file_ex return
  (data, errors, warnings, skipped); the 2-tuple names stay as wrappers
- One file-level line each for Day-vs--t disagreement and for labels
  skipped with no timepoint, capped at 10 named labels
- Standards and blanks stay silently skipped
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Surface warnings and the skip count on the endpoint

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py:442-463`
- Test: `tests/api/test_bulk_uploads.py`

**Interfaces:**
- Consumes: `ICPService.parse_and_process_icp_file_ex` (Task 2).
- Produces: no new symbols. `POST /api/bulk-uploads/icp-oes` populates the existing `UploadResponse.warnings` and a real `UploadResponse.skipped`.

**Context:** `UploadResponse` already declares `warnings: list[str] = []` and `skipped: int` (`backend/api/schemas/bulk_upload.py:95-98`). The endpoint currently passes no warnings and hardcodes `skipped=0`. No schema change and no frontend change are needed — the bulk-upload panel already renders `warnings`.

- [ ] **Step 1: Write the failing tests**

Unlike the two existing ICP endpoint tests, these deliberately do **not** mock
`backend.services.icp_service` — the point is to exercise the real parser through
the endpoint. `tests/conftest.py:9` already stubs
`frontend.config.variable_config` globally with the real
`ICP_FIXED_ELEMENT_FIELDS` list, so no `patch.dict` is needed. They use
`dry_run=true` and assert only on the response, so neither needs a seeded
experiment (`bulk_create_icp_results` may report an ingest error for the unknown
experiment; that is not what these tests are about).

Append to `tests/api/test_bulk_uploads.py`, near the other ICP tests:

```python
def _icp_csv(*labels: str) -> bytes:
    """Minimal 2-header-row ICP export with one Fe row per label."""
    rows = "\n".join(f"{label},Fe 238.204,10.0,1500,SAMP" for label in labels)
    return (
        "Header Row 1\nHeader Row 2\n"
        "Label,Element Label,Concentration,Intensity,Type\n"
        f"{rows}\n"
    ).encode("utf-8")


def test_icp_oes_returns_day_disagreement_warning(client):
    """A Day/-t disagreement is reported in warnings without rejecting the row."""
    resp = client.post(
        "/api/bulk-uploads/icp-oes",
        files={"file": ("icp.csv", io.BytesIO(_icp_csv(
            "SERUM_Cation_005c-t5_Day12_21x",
        )), "text/csv")},
        data={"dry_run": "true"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["warnings"]) == 1
    assert "-t token" in body["warnings"][0]
    assert "SERUM_Cation_005c-t5_Day12_21x" in body["warnings"][0]


def test_icp_oes_reports_skips_when_nothing_parses(client):
    """The early "ICP parse failed" return must carry warnings too. This is the
    whole-file labelling mistake, where the warning is the ONLY explanation for
    why nothing uploaded."""
    resp = client.post(
        "/api/bulk-uploads/icp-oes",
        files={"file": ("icp.csv", io.BytesIO(_icp_csv("HPHT_232_21x")), "text/csv")},
        data={"dry_run": "true"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["message"] == "ICP parse failed"
    assert body["skipped"] == 1
    assert len(body["warnings"]) == 1
    assert "HPHT_232_21x" in body["warnings"][0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/api/test_bulk_uploads.py -v -k "icp_upload_returns_disagreement or icp_upload_reports_skips"`

Expected: FAIL — `warnings` is `[]` and `skipped` is `0`.

- [ ] **Step 3: Thread warnings and the skip count through both return sites**

In `backend/api/routers/bulk_uploads.py`, replace lines 442-450:

```python
    try:
        processed_data, parse_errors, parse_warnings, skipped_count = (
            ICPService.parse_and_process_icp_file_ex(file_bytes)
        )
        if parse_errors and not processed_data:
            # This branch is the whole-file labelling mistake -- every label
            # skipped, so validate_icp_data reports "No data to validate" and the
            # gate fires. It MUST carry warnings: they are the only thing that
            # explains why nothing uploaded.
            return UploadResponse(created=0, updated=0, skipped=skipped_count,
                                  errors=parse_errors, warnings=parse_warnings,
                                  message="ICP parse failed")
        created_rows, updated_count, ingest_errors = ICPService.bulk_create_icp_results(
            db, processed_data, overwrite=overwrite
        )
        all_errors = parse_errors + ingest_errors
```

and the final `return UploadResponse(...)` at lines 459-463:

```python
    return UploadResponse(
        created=new_count, updated=updated_count, skipped=skipped_count,
        errors=all_errors, warnings=parse_warnings,
        message=_finalize_message(f"ICP-OES: {new_count} created, {updated_count} updated", dry_run),
        dry_run=dry_run,
    )
```

Leave the `except` branch at 452-456 untouched — a hard failure has no warnings to report.

- [ ] **Step 4: Re-point the two existing ICP endpoint mocks at the `_ex` name**

**This step is mandatory, not cleanup.** Both existing ICP endpoint tests mock the
service by attribute name:

```python
mock_icp.parse_and_process_icp_file.return_value = ([{"experiment_fk": 1}], [])
```

After Step 3 the router calls `parse_and_process_icp_file_ex`, which on a
`MagicMock` returns a plain `MagicMock`. Unpacking that into four names raises
`TypeError`, the router's `except Exception` catches it, and the endpoint returns
`{"message": "Upload failed"}`. Both tests would still *pass* — the shape test
already runs through the exception path (see its own comment at
`tests/api/test_bulk_uploads.py:437-442`), and `test_icp_oes_dry_run_rolls_back`
asserts `rollback` called once / `commit` not called, which the `except` branch
also satisfies. So `test_icp_oes_dry_run_rolls_back` would silently stop proving
dry-run behavior. Fix both:

At `tests/api/test_bulk_uploads.py:417`, change to:

```python
    mock_icp.parse_and_process_icp_file_ex.return_value = ([{"experiment_fk": 1}], [], [], 0)
```

At `tests/api/test_bulk_uploads.py:446`, change to:

```python
    mock_icp.parse_and_process_icp_file_ex.return_value = ([{"experiment_fk": 1}], [], [], 0)
```

Leave line 447's `bulk_create_icp_results` 3-tuple alone — it is already correct.
Do **not** "fix" the stale 2-tuple at line 418 in the shape test; that is
pre-existing and called out as out of scope in its sibling's docstring.

Then confirm `test_icp_oes_dry_run_rolls_back` now reaches the real success path:
its response body should report `created`/`updated` from the mock rather than
`{"message": "Upload failed"}`. Add one assertion to that test proving it:

```python
    assert body["message"].startswith("[DRY RUN] ICP-OES:")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/api/test_bulk_uploads.py -v -k icp`

Expected: PASS — the two new tests plus `test_icp_oes_returns_upload_response_shape` and `test_icp_oes_dry_run_rolls_back`.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/bulk_uploads.py tests/api/test_bulk_uploads.py
git commit -m "$(cat <<'EOF'
[fix] Return ICP label warnings from the endpoint

- Populate UploadResponse.warnings and a real skipped count
- The early "ICP parse failed" return carries warnings too, so a
  whole-file labelling mistake explains itself
- Re-point the two existing ICP mocks at parse_and_process_icp_file_ex
  so the dry-run test keeps proving dry-run, not the except branch
- No schema or frontend change; both fields already existed
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: End-to-end proof that the row lands on the ID's day

**Files:**
- Test: `tests/test_icp_handling.py` (append a new class after `TestICPLabelTimepointToken`)

**Interfaces:**
- Consumes: `ICPService.parse_and_process_icp_file_ex`, `ICPService.bulk_create_icp_results`, the `test_db` fixture at `tests/test_icp_handling.py:18-59`.
- Produces: nothing. This is the acceptance proof for spec §8.

**Why this is separate:** Tasks 1-3 prove the parser and the transport. This proves the defect is actually gone — that an `ICPResults` row physically hangs off the day-5 `ExperimentalResults` and not a day-12 one. Nothing above asserts against the database.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_icp_handling.py`:

```python
class TestICPTimepointTokenPersistence:
    """The ICP row must land on the ExperimentalResults for the ID's day."""

    def test_icp_row_is_written_at_the_id_token_day(self, test_db):
        exp = Experiment(
            experiment_id="SERUM_Cation_005c-t5",
            experiment_number=2,
            researcher="Test Researcher",
            date=datetime.now(),
            status="ONGOING",
        )
        test_db.add(exp)
        test_db.commit()

        csv = (
            "Header Row 1\nHeader Row 2\n"
            "Label,Element Label,Concentration,Intensity,Type\n"
            "SERUM_Cation_005c-t5_Day12_21x,Fe 238.204,10.0,1500,SAMP\n"
            "SERUM_Cation_005c-t5_Day12_21x,Ni 231.604,2.0,600,SAMP\n"
        ).encode("utf-8")

        data, errors, warnings, skipped = ICPService.parse_and_process_icp_file_ex(csv)
        assert errors == [], errors
        assert skipped == 0
        assert len(warnings) == 1

        created, updated, ingest_errors = ICPService.bulk_create_icp_results(test_db, data)
        assert ingest_errors == [], ingest_errors
        test_db.commit()

        rows = (
            test_db.query(ExperimentalResults)
            .filter(ExperimentalResults.experiment_fk == exp.id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].time_post_reaction_days == 5.0      # the ID's day, not 12
        assert rows[0].icp_data is not None
        assert rows[0].icp_data.dilution_factor == 21.0
        # dilution applied: 10.0 ppm * 21x
        assert rows[0].icp_data.fe == pytest.approx(210.0)

    def test_label_without_day_lands_on_the_same_day(self, test_db):
        exp = Experiment(
            experiment_id="SERUM_Cation_006a-t3",
            experiment_number=3,
            researcher="Test Researcher",
            date=datetime.now(),
            status="ONGOING",
        )
        test_db.add(exp)
        test_db.commit()

        csv = (
            "Header Row 1\nHeader Row 2\n"
            "Label,Element Label,Concentration,Intensity,Type\n"
            "SERUM_Cation_006a-t3_21x,Fe 238.204,10.0,1500,SAMP\n"
        ).encode("utf-8")

        data, errors, warnings, skipped = ICPService.parse_and_process_icp_file_ex(csv)
        assert errors == [], errors
        assert warnings == []       # no Day token, so nothing to disagree with

        _created, _updated, ingest_errors = ICPService.bulk_create_icp_results(test_db, data)
        assert ingest_errors == [], ingest_errors
        test_db.commit()

        rows = (
            test_db.query(ExperimentalResults)
            .filter(ExperimentalResults.experiment_fk == exp.id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].time_post_reaction_days == 3.0
        assert rows[0].icp_data is not None
```

- [ ] **Step 2: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_icp_handling.py::TestICPTimepointTokenPersistence -v`

Expected: PASS, given Tasks 1-2. If `time_post_reaction_days` reads 12.0, the parser change did not reach `create_icp_result` — check that `process_icp_dataframe_ex` builds `sample_info` from `info.time_post_reaction` and not from a stale `extract_sample_info` call.

If either test errors inside `bulk_create_icp_results` on SQLite (e.g. a savepoint or JSONB issue), STOP and report — do not weaken the assertion on `time_post_reaction_days`, which is the point of the task.

- [ ] **Step 3: Run the full backend suite touched by this change**

Run, one process at a time:

```bash
.venv/Scripts/python -m pytest tests/test_icp_handling.py tests/api/test_bulk_uploads.py tests/test_time_field_guardrails.py -v
```

Expected: PASS. Note `tests/test_pg_backup_restore.py` has 3 pre-existing failures unrelated to this work; do not include it and do not attempt to fix it.

- [ ] **Step 4: Commit**

```bash
git add tests/test_icp_handling.py
git commit -m "$(cat <<'EOF'
[fix] Assert ICP rows land on the ID token's day

- End-to-end: a _Day12 label on a -t5 vial writes one result at day 5
- Covers the no-Day label shape too
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Documentation and the locked-parser footnote

**Files:**
- Modify: `docs/upload_templates/icp_oes_upload.md:26-31`
- Modify: `docs/LOCKED_COMPONENTS.md` (the `icp_service.py` row at line 52, plus a new footnote after ² which ends around line 73)
- Modify: `MODELS.md` (the `id_timepoint_days` bullet, which currently names only the scalar/master parsers)
- Modify: `docs/working/issue-log.md` (append an entry)

**Interfaces:** none — documentation only.

**Note:** a `PostToolUse` hook copies anything written under `docs/` into `docs/project_context/`, excluding `docs/working/` and `docs/superpowers/`. Never edit `docs/project_context/` by hand; after editing the two `docs/` files above, `git status` will show their `project_context` copies as modified and they must be staged in the same commit.

- [ ] **Step 1: Rewrite the label-parsing section of the upload template**

In `docs/upload_templates/icp_oes_upload.md`, replace the `### Sample Identification (Label Parsing)` section (lines 26-31) with:

```markdown
### Sample Identification (`Label` Parsing)

The `Label` column is parsed right-to-left:

1. `_<N>x` dilution token — **required** (the trailing `x` is optional).
2. An optional `_Day<N>` or `_Time<N>` token.
3. Whatever remains is the experiment ID.

**The experiment ID's trailing `-t<days>` token wins.** A destructively-sampled
vial encodes its own day in its ID (`SERUM_Cation_005c-t5`), and that day is
canonical. When the ID carries the token, any `Day<n>` in the label is ignored —
the upload reports the disagreement in its warnings but writes every row.

| Label | Experiment | Day | Dilution |
|---|---|---|---|
| `SERUM_Cation_005c-t5_21x` | `SERUM_Cation_005c-t5` | 5 (from ID) | 21 |
| `SERUM_Cation_005c-t5_Day12_21x` | `SERUM_Cation_005c-t5` | 5 (from ID; `Day12` ignored, warned) | 21 |
| `HPHT_231_Day6_21x` | `HPHT_231` | 6 (from label) | 21 |
| `Serum_MH_011_Day5_5x` | `Serum_MH_011` | 5 (from label) | 5 |

A label with **no** timepoint from either source is skipped and named in the
upload's warnings — for example `HPHT_231_21x`, or `SERUM_Cation_005c-T5_21x`,
because **the timepoint token is lowercase `-t` only**. Standards and blanks
(`Standard 1`, `Blank`) are skipped silently, as before.
```

- [ ] **Step 2: Add footnote ³ to LOCKED_COMPONENTS.md**

Change the table row at line 52 to carry the marker:

```markdown
| `icp_service.py` | Raw ICP-OES CSV, delimiter detection, dilution correction |³
```

Then append after footnote ²:

```markdown
³ **Label timepoint contract (changed 2026-08-07 with explicit sign-off).** The
`Label` column's `_Day<n>` token no longer determines a result's timepoint when the
experiment ID carries a `-t<days>` token: the ID wins, the disagreement is reported
in `warnings`, and no row is rejected. This matches `master_bulk_upload.py` (see ²
and its `:383` comment) and deliberately differs from `POST /api/results`, which
still 400s via `apply_id_timepoint`. Three properties are load-bearing when
touching `extract_sample_info_ex`: (a) the `-t` grammar is delegated to
`database/experiment_id_parser.py::split_timepoint_token` and must never be
re-implemented here, or ICP drifts from lineage; (b) dilution is peeled **before**
the token is split, so `-t<days>` is at end-of-string when the anchored regex runs;
(c) `extract_sample_info` must keep returning exactly three keys, because
`create_icp_result` splats it into `result_data` and stores every unrecognized key
in the `all_elements` JSONB as a fake element. See
`docs/superpowers/specs/2026-08-07-icp-label-timepoint-token-design.md` and
`tests/test_icp_handling.py::TestICPLabelTimepointToken`.
```

- [ ] **Step 3: Extend the `id_timepoint_days` bullet in MODELS.md**

Find the sentence in the `id_timepoint_days` bullet reading "The ID is canonical for the vial's timepoint: result creation fills a blank time from it and rejects a conflicting one (guards in `create_scalar_result_ex` and `POST /api/results`; string-level checks in the scalar/master bulk parsers)." Append to that bullet:

```markdown
    The **ICP-OES upload** also honors the token, but *reports* rather than
    rejects: `extract_sample_info_ex` (`backend/services/icp_service.py`) takes the
    day from the ID's `-t` token and emits one file-level warning when the label's
    `_Day<n>` disagrees, matching `master_bulk_upload.py` rather than
    `apply_id_timepoint`. A label may therefore omit `Day` entirely
    (`SERUM_Cation_005c-t5_21x`); one with neither a `-t` token nor a `Day` token is
    skipped and named in the warnings. Changed 2026-08-07 — see footnote ³ in
    `docs/LOCKED_COMPONENTS.md`.
```

- [ ] **Step 4: Append the issue-log entry**

Append to `docs/working/issue-log.md`, matching the format of the entries already there:

```markdown
## 2026-08-07 — ICP label timepoint: `-t<days>` wins over `_Day<n>`

- **Audit finding:** the ID does **not** fail to parse. `extract_sample_info`'s regex
  is end-anchored, so `SERUM_Cation_005c-t5_Day12_21x` correctly yields
  `SERUM_Cation_005c-t5`. What broke is the timepoint: `Day12` became the result's
  day while the vial's ID declared day 5, and `icp_service.py` is the one write path
  that never called `apply_id_timepoint`, so nothing raised.
- **Measured before the change (dev DB, 2026-08-07):** 969 `icp_results` rows, of
  which **0** carry a `-t` token in `raw_label` and 969 carry `_Day`/`_Time`;
  167 of 1009 experiments are `-t` vials across 82 distinct stems, **0** of which
  have a bare experiment row; **0** ICP results were attached to any `-t` vial. The
  failure was entirely prospective — no backfill was needed.
- **Decisions (user, 2026-08-07):** the ID wins silently on the row (never
  rejected); `Day` becomes optional when `-t` is present; labels with no timepoint
  are reported as warnings; and the disagreement gets **one file-level warning**,
  aligning with `master_bulk_upload.py:766` after that precedent was surfaced.
- **Locked component:** `icp_service.py` (`docs/LOCKED_COMPONENTS.md:52`) — explicit
  sign-off given; recorded as footnote ³.
- **Scope notes — deliberately not fixed:**
  1. `_find_experiment` (`icp_service.py:769`) still uses its own naive
     strip-and-concatenate key plus `.first()` rather than
     `_id_match.normalize_id` / `find_experiment_matches`. It is *stricter* on zero
     padding than the canonical key, so `SERUM_Catalyst_1a-t7` will not match stored
     `SERUM_Catalyst_001a-t7`. Measured 0 collisions across all 1009 experiments.
  2. `-T5` / `_t5` spellings remain unaccepted — widening them changes the
     repo-wide ID grammar, already scoped to its own task. They now land in the
     *reported* skip bucket rather than vanishing.
  3. `tests/test_icp_parsing.py` and `tests/test_icp_service.py` are print-only
     scripts (the former re-implements the parser locally and asserts nothing).
     Left untouched; real coverage went into `tests/test_icp_handling.py`.
- **Tests added:** yes — `tests/test_icp_handling.py::TestICPLabelTimepointToken`
  and `::TestICPTimepointTokenPersistence`, plus two endpoint tests in
  `tests/api/test_bulk_uploads.py`.
- **Docs updated:** yes.
```

- [ ] **Step 5: Verify the doc-sync hook fired and stage everything**

Run: `git status --short`

Expected: modifications to `docs/upload_templates/icp_oes_upload.md`, `docs/LOCKED_COMPONENTS.md`, `MODELS.md`, `docs/working/issue-log.md`, **and** the hook's copies `docs/project_context/icp_oes_upload.md` and `docs/project_context/LOCKED_COMPONENTS.md`. `docs/working/` and `docs/superpowers/` must NOT be copied.

If a `project_context` copy is missing, do not create it by hand — re-run the corresponding `Edit` so the hook fires.

- [ ] **Step 6: Run the full affected suite one final time**

Run: `.venv/Scripts/python -m pytest tests/test_icp_handling.py tests/api/test_bulk_uploads.py tests/test_time_field_guardrails.py -v`

Expected: PASS. Report the actual summary line; do not claim success without it.

- [ ] **Step 7: Commit**

```bash
git add docs/upload_templates/icp_oes_upload.md docs/LOCKED_COMPONENTS.md MODELS.md docs/working/issue-log.md docs/project_context/
git commit -m "$(cat <<'EOF'
[fix] Document the ICP label timepoint contract

- Upload template: new right-to-left label grammar and examples
- LOCKED_COMPONENTS footnote 3 for the icp_service.py sign-off
- MODELS.md: ICP reports rather than rejects a -t disagreement
- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Acceptance criteria (from spec §8)

- [ ] `SERUM_Cation_005c-t5_Day12_21x` writes its ICP row at day **5**, not 12 (Task 4)
- [ ] `SERUM_Cation_005c-t5_21x` (no `Day`) parses and writes at day 5 (Tasks 1, 4)
- [ ] `HPHT_231_Day6_21x` and `Serum_MH_011_Day5_5x` behave exactly as before (Task 1)
- [ ] A `Day`/`-t` disagreement produces exactly **one** file-level warning, capped at 10 named labels, and rejects **no** row (Task 2)
- [ ] A label with no time source is skipped, counted in `skipped`, and named in a warning (Tasks 2, 3)
- [ ] `Standard 1` / `Blank` remain silently skipped (Tasks 1, 2)
- [ ] `extract_sample_info` still returns exactly three keys (Task 1)
- [ ] `warnings` and a real `skipped` reach `UploadResponse` with no schema or frontend change (Task 3)
- [ ] A file whose every label is skipped still returns its skip warning (Task 3)
- [ ] Footnote ³ added to `docs/LOCKED_COMPONENTS.md` (Task 5)
