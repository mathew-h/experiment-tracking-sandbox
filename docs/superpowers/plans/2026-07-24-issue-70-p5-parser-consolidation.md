# Issue #70 P5 — Parser Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the two duplicate experiment-ID parsers (`database/lineage_utils.py::parse_experiment_id` and `backend/services/experiment_validation.py::parse_experiment_id`/`extract_lineage_info`) onto one canonical module, and wire `SERUM_001a-2` → `SERUM_001a` parent links — with no other behavior change anywhere.

**Architecture:** A new module `database/experiment_id_parser.py` becomes the single source of truth for the experiment-ID grammar (the P1 replicate ruleset, moved verbatim from `lineage_utils`) and for base-stem classification (type / researcher initials / index / validity / warnings, moved verbatim from `experiment_validation`). It exposes `parse_lineage_fields()` (4-tuple), `classify_base_id()`, and `parse_experiment_id_full()` (the full `ParsedExperimentID` the issue asks for). `lineage_utils.parse_experiment_id` becomes a thin delegating wrapper (same signature, same behavior — all callers and tests untouched). `experiment_validation.parse_experiment_id` delegates classification to the canonical module but keeps `extract_lineage_info` **frozen verbatim as a documented legacy shim**, because its behavior diverges from the canonical grammar on real inputs and that divergent behavior is consumed by locked code (see "Why extract_lineage_info cannot be collapsed" below). The sanctioned behavior change (letter+sequential parent wiring) lands in `lineage_utils.update_experiment_lineage`.

**Tech Stack:** Python 3 / SQLAlchemy ORM / pytest. No new packages, no schema change, no Alembic migration, no frontend change.

## Global Constraints

- **The only sanctioned behavior change** is issue #70 P5's parent wiring: `SERUM_001a-2` links to `SERUM_001a` as parent. Everything else must be byte-identical in behavior. Anything that looks like a fix opportunity gets logged in the "Logged, not fixed" section of this plan — never fixed.
- **All previous parser tests pass unchanged.** Do not edit any existing assertion in `tests/test_lineage_migration.py`, `tests/test_replicate_lineage.py`, `tests/services/test_experiment_validation_replicates.py`, or any other existing test file. New tests are added in new classes/files only (one existing file gains a new class, no existing lines change).
- **`backend/services/bulk_uploads/new_experiments.py` is a locked component.** Issue #70 authorizes only mechanical call-site updates. This plan requires **zero edits** to it — its imports (`parse_experiment_id as parse_exp_id_validation`, `validate_experiment_id`, `extract_lineage_info` from `backend.services.experiment_validation`) keep resolving to functions with identical behavior. If any task finds an edit unavoidable, STOP and report — do not improvise.
- **`database/data_migrations/establish_experiment_lineage_006.py` is frozen.** Its classification logic was deliberately left pre-replicate (decision logged 2026-07-23 in `docs/working/decisions.md`). This plan requires **zero edits** to it: it imports `parse_experiment_id` and `get_or_find_parent_experiment` from `database.lineage_utils`, both of which keep identical signatures and behavior. For the same reason, **`get_or_find_parent_experiment` must not change at all** — the new parent wiring lives only in `update_experiment_lineage`.
- **`extract_lineage_info`'s function body is frozen.** Only its docstring may change (Task 2 documents its legacy status and corrects one stale docstring example that contradicts pinned actual behavior — doctests are not collected by pytest in this repo, so docstring examples are documentation only).
- **Commit format:** `[#70] <imperative, ≤50 chars>` with `- Tests added: yes/no` / `- Docs updated: yes/no` detail lines (repo CLAUDE.md section 8).
- **Test command:** `.venv/Scripts/python -m pytest <path> -q` from the repo root. Full-suite runs are expected to show exactly 3 pre-existing failures in `tests/test_pg_backup_restore.py` (local pg_dump toolchain gap, predates this branch) and 4 skips. Any other failure is a defect in this branch.
- **No writes to `docs/project_context/`** — the PostToolUse hook syncs `docs/` files automatically.
- Branch: `refactor/issue-70-p5-parser-consolidation` (already created from `develop`).

## Why `extract_lineage_info` cannot be collapsed (read before Task 1)

The issue's default assumption is that the two parsers duplicate one delimiter logic. Research found they implement **different algorithms with divergent outputs on the same inputs**, and both behaviors are contractually pinned:

1. **Combined sequential+treatment (documented pre-existing bug, predates issue #69):**
   `lineage_utils.parse_experiment_id("Serum_MH_101-2_Desorption")` → `("Serum_MH_101", 2, "Desorption", None)` — pinned by `tests/test_replicate_lineage.py::test_existing_combined_sequential_treatment_unaffected` and `tests/test_lineage_migration.py` line 170.
   `extract_lineage_info("Serum_MH_101-2_Desorption")` → `("Serum_MH_101-2", None, "Desorption", None)` — pinned by `tests/services/test_experiment_validation_replicates.py::test_existing_combined_unaffected`, which explicitly documents the bug and pins the buggy output.
   One function cannot return both tuples for the same input.

2. **Naive trailing `-N` rule (newly surfaced during P5 research, previously undocumented):**
   `lineage_utils.parse_experiment_id("CF-015")` → `("CF-015", None, None, None)` (guarded: `-N` is sequential only when the prefix ends in a numeric segment) — pinned by `tests/test_lineage_migration.py` lines 149-154 and `tests/test_replicate_lineage.py` line 46.
   `extract_lineage_info("CF-015")` → `("CF", 15, None, None)` (any trailing `-N` is sequential).
   This is not a dead branch: `new_experiments.py` line 374 (`elif parsed.sequential_number or parsed.treatment_variant:`) and `find_parent_for_copy` (line 43) consume the legacy semantics for real Core Flood IDs (`CF-015`, `CF-04` exist in production data per `fix_stale_lineage`'s docstring). Switching the validation surface to canonical semantics would change which upload rows get the "created without parent" warning — a real behavior change, prohibited.

**Resolution (per the pre-authorized default in the task briefing):** pin the current behavior with tests and document it as a known issue. The canonical module owns the grammar; `extract_lineage_info` survives verbatim as an explicitly-deprecated legacy shim used only by its two existing consumers (`find_parent_for_copy` and `experiment_validation.parse_experiment_id`'s lineage-field extraction). The genuinely duplicated *classification* half (type/initials/index/validity/warnings — ~50 lines) IS collapsed into the canonical module. Both divergences above get new pinning tests (Task 2).

## Logged, not fixed (known issues surfaced by this work — do NOT fix any of these)

1. `extract_lineage_info` combined `-N_Treatment` bug (item 1 above) — pinned, documented in its docstring by Task 2.
2. `extract_lineage_info` naive trailing `-N` rule (item 2 above) — pinned by new tests in Task 2, documented in its docstring.
3. `extract_lineage_info`'s docstring example for `HPHT_001-2_Desorption` claims `("HPHT_001", 2, "Desorption", None)` but actual behavior is `("HPHT_001-2", None, "Desorption", None)` — stale doc, corrected (docstring-only) in Task 2.
4. Insertion-order limitation of the new wiring: if `SERUM_001a-2` is created while neither `SERUM_001a` nor the stem exists, it is orphaned; when the stem is later created, `update_orphaned_derivations` links it to the **stem** (it is letter-unaware), even if `SERUM_001a` was created in between (a lettered replicate insert does not trigger orphan re-linking). Documented in MODELS.md by Task 4; not fixed.
5. `get_or_find_parent_experiment`'s candidate loop treats lettered replicates (`cand_seq is None`) the same as the bare base, so its "base" pick among candidates is query-order-dependent when lettered siblings exist. Pre-existing, unreached by the live replicate path (the replicate branch of `update_experiment_lineage` intercepts first), and the function is frozen for the migration script's sake. Not touched.
6. Exotic shapes (e.g. `Foo_Bar_Desorption-2`) diverge further between the two algorithms — inherent to keeping the legacy shim; noted in the shim's docstring, not enumerated exhaustively.

## File Structure

- **Create:** `database/experiment_id_parser.py` — canonical grammar + classification + full parse (no imports from `backend/`; imports `ExperimentType` from `database.models.enums` only).
- **Create:** `tests/test_experiment_id_parser.py` — unit tests for the canonical module + cross-surface equivalence pins.
- **Modify:** `database/lineage_utils.py` — `parse_experiment_id` becomes a delegating wrapper (grammar body and module regexes move out); `update_experiment_lineage` gains letter+sequential parent wiring.
- **Modify:** `backend/services/experiment_validation.py` — dataclass/type-map/classification move to canonical module (re-exported here for compatibility); `parse_experiment_id` delegates classification; `extract_lineage_info` body untouched, docstring rewritten.
- **Modify:** `tests/services/test_experiment_validation_replicates.py` — new class appended (divergence pins); no existing lines change.
- **Modify:** `tests/test_replicate_lineage.py` — new class appended (wiring tests); no existing lines change.
- **Modify (docs):** `.claude/rules/MODELS.md`, `docs/working/decisions.md`, `docs/user_guide/REPLICATES.md`.
- **Zero-edit (verify only):** `backend/services/bulk_uploads/new_experiments.py`, `database/data_migrations/establish_experiment_lineage_006.py`, `database/event_listeners.py`, `backend/services/bulk_uploads/replicate_routing.py`, `tests/check_lineage_integrity.py`, `legacy/streamlit_frontend/new_experiment.py` — all keep working through the preserved import surfaces.

---

### Task 1: Canonical parser module + lineage_utils delegation

**Files:**
- Create: `database/experiment_id_parser.py`
- Create: `tests/test_experiment_id_parser.py`
- Modify: `database/lineage_utils.py` (lines 13-14 imports, 22-23 regexes, 26-121 `parse_experiment_id`)

**Interfaces:**
- Consumes: `database.models.enums.ExperimentType` (existing enum).
- Produces (later tasks and callers rely on these exact names):
  - `database.experiment_id_parser.parse_lineage_fields(experiment_id) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[str]]` — byte-identical behavior to today's `lineage_utils.parse_experiment_id`.
  - `database.experiment_id_parser.classify_base_id(base_id: str, original_id: str) -> Tuple[Optional[ExperimentType], Optional[str], Optional[str], bool, List[str]]` — returns `(experiment_type, researcher_initials, index, is_valid, warnings)`.
  - `database.experiment_id_parser.parse_experiment_id_full(experiment_id) -> ParsedExperimentID`.
  - `database.experiment_id_parser.ParsedExperimentID` (dataclass, moved verbatim from `experiment_validation` — same field names/order/defaults).
  - `database.experiment_id_parser.get_experiment_type_from_id`, `database.experiment_id_parser.EXPERIMENT_TYPE_ABBREVIATIONS` (moved verbatim).
  - `database.lineage_utils.parse_experiment_id` — unchanged signature/behavior (now delegates).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_experiment_id_parser.py`:

```python
"""Tests for the canonical experiment ID parser (issue #70 P5).

parse_lineage_fields / parse_experiment_id_full encode the final replicate
ruleset (P1 grammar). The legacy divergent surface (extract_lineage_info)
is pinned separately in tests/services/test_experiment_validation_replicates.py.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.experiment_id_parser import (
    ParsedExperimentID,
    classify_base_id,
    get_experiment_type_from_id,
    parse_experiment_id_full,
    parse_lineage_fields,
)
from database.models.enums import ExperimentType


class TestParseLineageFields:
    """Byte-identical to the pre-P5 lineage_utils.parse_experiment_id grammar."""

    def test_bare_stems(self):
        assert parse_lineage_fields("HPHT_MH_001") == ("HPHT_MH_001", None, None, None)
        assert parse_lineage_fields("LEACH_TEST") == ("LEACH_TEST", None, None, None)
        assert parse_lineage_fields("SERUM_001") == ("SERUM_001", None, None, None)

    def test_sequential(self):
        assert parse_lineage_fields("HPHT_MH_001-2") == ("HPHT_MH_001", 2, None, None)
        assert parse_lineage_fields("HPHT_MH_001-10") == ("HPHT_MH_001", 10, None, None)
        assert parse_lineage_fields("HPHT_001-2") == ("HPHT_001", 2, None, None)

    def test_type_prefixed_ids_are_standalone(self):
        assert parse_lineage_fields("CF-015") == ("CF-015", None, None, None)
        assert parse_lineage_fields("CF-12") == ("CF-12", None, None, None)
        assert parse_lineage_fields("CF-04") == ("CF-04", None, None, None)
        assert parse_lineage_fields("CF-015-2") == ("CF-015", 2, None, None)

    def test_hyphenated_non_derivations(self):
        assert parse_lineage_fields("COMPLEX-ID-TEST-3") == ("COMPLEX-ID-TEST-3", None, None, None)
        assert parse_lineage_fields("TEST-SAMPLE-001") == ("TEST-SAMPLE-001", None, None, None)
        assert parse_lineage_fields("TEST-SAMPLE-ABC") == ("TEST-SAMPLE-ABC", None, None, None)
        assert parse_lineage_fields("HPHT-HIGH-TEMP") == ("HPHT-HIGH-TEMP", None, None, None)

    def test_treatment(self):
        assert parse_lineage_fields("HPHT_MH_001_Desorption") == ("HPHT_MH_001", None, "Desorption", None)
        assert parse_lineage_fields("Serum_MH_101_Annealing") == ("Serum_MH_101", None, "Annealing", None)

    def test_combined_sequential_treatment(self):
        assert parse_lineage_fields("HPHT_MH_001-2_Desorption") == ("HPHT_MH_001", 2, "Desorption", None)
        assert parse_lineage_fields("Serum_MH_101-3_Annealing") == ("Serum_MH_101", 3, "Annealing", None)

    def test_explicit_parent_spellings(self):
        assert parse_lineage_fields("HPHT_MH_001-0") == ("HPHT_MH_001", 0, None, None)
        assert parse_lineage_fields("HPHT_MH_001-1") == ("HPHT_MH_001", 1, None, None)

    def test_replicate_letters(self):
        assert parse_lineage_fields("SERUM_001a") == ("SERUM_001", None, None, "a")
        assert parse_lineage_fields("Serum_MH_101a") == ("Serum_MH_101", None, None, "a")
        assert parse_lineage_fields("SERUM_001a-2") == ("SERUM_001", 2, None, "a")

    def test_empty_and_none(self):
        assert parse_lineage_fields("") == (None, None, None, None)
        assert parse_lineage_fields(None) == (None, None, None, None)
        assert parse_lineage_fields("   ") == (None, None, None, None)


class TestLineageUtilsDelegation:
    """lineage_utils.parse_experiment_id must remain the same public surface."""

    def test_wrapper_matches_canonical_on_corpus(self):
        from database.lineage_utils import parse_experiment_id
        corpus = [
            "HPHT_MH_001", "LEACH_TEST", "SERUM_001", "HPHT_MH_001-2",
            "HPHT_001-2", "CF-015", "CF-015-2", "TEST-SAMPLE-001",
            "HPHT-HIGH-TEMP", "HPHT_MH_001_Desorption",
            "HPHT_MH_001-2_Desorption", "SERUM_001-0", "SERUM_001-1",
            "SERUM_001a", "Serum_MH_101a", "SERUM_001a-2",
            "SERUM_001a-2_Desorption", "", None, "   ",
        ]
        for exp_id in corpus:
            assert parse_experiment_id(exp_id) == parse_lineage_fields(exp_id), exp_id


class TestClassifyBaseId:
    def test_three_part(self):
        etype, initials, index, is_valid, warnings = classify_base_id("Serum_MH_101", "Serum_MH_101")
        assert etype == ExperimentType.SERUM
        assert initials == "MH"
        assert index == "101"
        assert is_valid is True
        assert warnings == []

    def test_two_part(self):
        etype, initials, index, is_valid, warnings = classify_base_id("HPHT_001", "HPHT_001")
        assert etype == ExperimentType.HPHT
        assert initials is None
        assert index == "001"
        assert is_valid is True
        assert warnings == []

    def test_one_part_invalid(self):
        etype, initials, index, is_valid, warnings = classify_base_id("CF-015", "CF-015")
        assert etype is None and initials is None and index is None
        assert is_valid is False
        assert len(warnings) == 1
        assert "Got: CF-015" in warnings[0]

    def test_unknown_type_warning(self):
        etype, initials, index, is_valid, warnings = classify_base_id("XYZ_001", "XYZ_001")
        assert etype is None
        assert index == "001"
        assert is_valid is False
        assert any("Unknown experiment type 'XYZ'" in w for w in warnings)


class TestParseExperimentIdFull:
    def test_replicate_full_parse(self):
        result = parse_experiment_id_full("Serum_MH_101a-2")
        assert isinstance(result, ParsedExperimentID)
        assert result.experiment_type == ExperimentType.SERUM
        assert result.researcher_initials == "MH"
        assert result.index == "101"
        assert result.replicate_label == "a"
        assert result.sequential_number == 2
        assert result.treatment_variant is None
        assert result.base_id == "Serum_MH_101"
        assert result.original_id == "Serum_MH_101a-2"
        assert result.is_valid is True
        assert result.warnings == []

    def test_combined_sequential_treatment_uses_canonical_grammar(self):
        # Unlike the legacy validation surface, the canonical full parse
        # extracts BOTH the sequential number and the treatment.
        result = parse_experiment_id_full("HPHT_001-2_Desorption")
        assert result.sequential_number == 2
        assert result.treatment_variant == "Desorption"
        assert result.base_id == "HPHT_001"
        assert result.index == "001"

    def test_cf_shape_is_standalone_and_invalid_format(self):
        result = parse_experiment_id_full("CF-015")
        assert result.sequential_number is None
        assert result.base_id == "CF-015"
        assert result.is_valid is False

    def test_empty_is_invalid(self):
        for bad in ("", None, "   "):
            result = parse_experiment_id_full(bad)
            assert result.is_valid is False
            assert result.warnings == ["Experiment ID is empty or invalid"]
            assert result.replicate_label is None

    def test_type_map(self):
        assert get_experiment_type_from_id("ac") == ExperimentType.AUTOCLAVE
        assert get_experiment_type_from_id("CF") == ExperimentType.CF
        assert get_experiment_type_from_id("nonsense") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_experiment_id_parser.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'database.experiment_id_parser'`

- [ ] **Step 3: Create `database/experiment_id_parser.py`**

The grammar body below is moved **verbatim** from `database/lineage_utils.py` lines 73-121 (function `parse_experiment_id`) and the classification branching **verbatim** from `backend/services/experiment_validation.py` lines 244-299; the dataclass and type map are moved verbatim from lines 28-79 of the same file. Do not "improve" any moved logic.

```python
"""
Canonical experiment ID parser (issue #70 P5).

Single source of truth for the experiment ID grammar:

- ``TYPE_INDEX`` (2-part, e.g. ``HPHT_001``) or ``TYPE_INITIALS_INDEX``
  (3-part, e.g. ``Serum_MH_101``) base stems
- ``-N`` sequential derivations (only when the prefix ends in a numeric
  segment, so ``CF-015`` stays standalone); ``-0``/``-1`` are explicit
  "group parent" spellings (see lineage_utils.update_experiment_lineage)
- ``_Text`` treatment variants (e.g. ``_Desorption``)
- a single trailing lowercase letter bound to the numeric index for
  replicates (e.g. ``SERUM_001a``), issue #69/#70 grammar

Consumers:
- ``database.lineage_utils.parse_experiment_id`` delegates to
  :func:`parse_lineage_fields` (4-tuple surface used by lineage, event
  listeners, replicate routing, and the data-migration script).
- ``backend.services.experiment_validation.parse_experiment_id`` delegates
  its classification half to :func:`classify_base_id` but keeps its OWN
  legacy lineage extraction (``extract_lineage_info``), whose divergent
  behavior is pinned — see that function's docstring.
- :func:`parse_experiment_id_full` returns the complete parse in one call.

This module must not import anything from ``backend``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from database.models.enums import ExperimentType


# Mapping of common abbreviations to ExperimentType enum values
EXPERIMENT_TYPE_ABBREVIATIONS: Dict[str, ExperimentType] = {
    # Full names (case-insensitive)
    "serum": ExperimentType.SERUM,
    "autoclave": ExperimentType.AUTOCLAVE,
    "hpht": ExperimentType.HPHT,
    "coreflood": ExperimentType.CF,
    "core flood": ExperimentType.CF,
    "cf": ExperimentType.CF,
    "other": ExperimentType.OTHER,
    # Common abbreviations
    "ac": ExperimentType.AUTOCLAVE,
}


@dataclass
class ParsedExperimentID:
    """Result of parsing an experiment ID."""
    experiment_type: Optional[ExperimentType]
    researcher_initials: Optional[str]
    index: Optional[str]
    sequential_number: Optional[int]
    treatment_variant: Optional[str]
    base_id: str  # The ID without sequential/treatment suffixes
    original_id: str
    is_valid: bool
    warnings: List[str]
    replicate_label: Optional[str] = None  # "a", "b", "c"; None = not a replicate


_REPLICATE_LETTER_RE = re.compile(r'^(\d+)([a-z])$')
_REPLICATE_GUARD_RE = re.compile(r'^\d+[a-z]$')


def get_experiment_type_from_id(type_text: str) -> Optional[ExperimentType]:
    """
    Map experiment type text (abbreviation or full name) to ExperimentType enum.

    Args:
        type_text: The type portion from experiment ID (case-insensitive)

    Returns:
        ExperimentType enum value if found, None otherwise
    """
    if not type_text:
        return None

    normalized = type_text.strip().lower()
    return EXPERIMENT_TYPE_ABBREVIATIONS.get(normalized)


def parse_lineage_fields(experiment_id: str) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[str]]:
    """
    Parse an experiment ID to extract the base ID, derivation number, treatment variant,
    and replicate label.

    Uses hybrid delimiter system:
    - Hyphen-NUMBER for sequential lineage (e.g., -2, -3), but ONLY when the prefix
      itself ends in a numeric segment (_NNN or -NNN, optionally letter-suffixed).
    - Underscore-TEXT for treatment variants (e.g., _Desorption).
    - A single trailing lowercase letter bound to the numeric index for replicates
      (e.g., _001a). Extracted last so a letter-suffixed index is never mistaken
      for a treatment name.

    TYPE-NNN IDs (e.g., CF-015, CF-04) are treated as standalone base experiments
    because their prefix ("CF") does not end in digits.

    -0 and -1 are valid derivation numbers (they denote the explicit "group parent"
    spelling of a replicate set — see database/lineage_utils.py::update_experiment_lineage).

    Args:
        experiment_id: The experiment ID to parse

    Returns:
        A tuple of (base_experiment_id, derivation_number, treatment_variant, replicate_label)

    Examples:
        >>> parse_lineage_fields("CF-015")
        ("CF-015", None, None, None)
        >>> parse_lineage_fields("CF-015-2")
        ("CF-015", 2, None, None)
        >>> parse_lineage_fields("HPHT_MH_001-2")
        ("HPHT_MH_001", 2, None, None)
        >>> parse_lineage_fields("HPHT_MH_001-2_Desorption")
        ("HPHT_MH_001", 2, "Desorption", None)
        >>> parse_lineage_fields("HPHT_MH_001")
        ("HPHT_MH_001", None, None, None)
        >>> parse_lineage_fields("HPHT_MH_001_Desorption")
        ("HPHT_MH_001", None, "Desorption", None)
        >>> parse_lineage_fields("SERUM_001-0")
        ("SERUM_001", 0, None, None)
        >>> parse_lineage_fields("SERUM_001a")
        ("SERUM_001", None, None, "a")
        >>> parse_lineage_fields("Serum_MH_101a")
        ("Serum_MH_101", None, None, "a")
        >>> parse_lineage_fields("SERUM_001a-2")
        ("SERUM_001", 2, None, "a")
    """
    if not experiment_id or not isinstance(experiment_id, str):
        return None, None, None, None

    experiment_id = experiment_id.strip()
    if not experiment_id:
        return None, None, None, None

    treatment_variant = None
    derivation_num = None
    replicate_label = None
    base_id = experiment_id

    # Step 1: Extract treatment variant (trailing _TEXT segment).
    # A trailing underscore segment is a treatment only when:
    #   - it is not a letter-suffixed numeric index (e.g. "101a") — replicate guard
    #   - it contains no hyphens (so "001-2" is not mistaken for a treatment)
    #   - it is not all digits (so "001" index segments are left alone)
    #   - removing it still leaves a structured ID with >= 2 underscore-segments
    #     (prevents "CF_Desorption" from stripping "Desorption" off a 1-part base)
    parts = experiment_id.split('_')
    if len(parts) >= 2:
        last = parts[-1]
        if not _REPLICATE_GUARD_RE.match(last) and not last.isdigit() and '-' not in last:
            remaining = '_'.join(parts[:-1])
            if len(remaining.split('_')) >= 2:
                treatment_variant = last
                base_id = remaining

    # Step 2: Extract sequential derivation number (trailing -N).
    # Only treat -N as a derivation when the prefix already ends in _NNN or -NNN
    # (optionally letter-suffixed, e.g. "_001a"), confirming it carries a numeric index.
    # This prevents TYPE-NNN IDs like CF-015 from being parsed as deriv=15 of "CF".
    # -0 and -1 are valid derivation numbers (see docstring).
    if '-' in base_id:
        prefix, _, suffix = base_id.rpartition('-')
        if suffix.isdigit() and re.search(r'[_-]\d+[a-z]?$', prefix):
            derivation_num = int(suffix)
            base_id = prefix

    # Step 3: Extract the replicate letter bound to the numeric index and rebuild
    # base_id with the numeric-only index (e.g. "SERUM_001a" -> "SERUM_001").
    id_parts = base_id.split('_')
    letter_match = _REPLICATE_LETTER_RE.match(id_parts[-1])
    if letter_match:
        replicate_label = letter_match.group(2)
        id_parts[-1] = letter_match.group(1)
        base_id = '_'.join(id_parts)

    return base_id, derivation_num, treatment_variant, replicate_label


def classify_base_id(base_id: str, original_id: str) -> Tuple[Optional[ExperimentType], Optional[str], Optional[str], bool, List[str]]:
    """
    Classify a base stem into (experiment_type, researcher_initials, index,
    is_valid, warnings).

    Supports both 2-part (TYPE_INDEX) and 3-part (TYPE_INITIALS_INDEX) formats.
    ``original_id`` is only used in warning text. Warning strings are pinned —
    they surface verbatim in bulk-upload row feedback.
    """
    warnings: List[str] = []

    parts = base_id.split('_')

    experiment_type = None
    researcher_initials = None
    index = None

    if len(parts) < 2:
        warnings.append(
            f"Expected format: ExperimentType_Index or ExperimentType_ResearcherInitials_Index "
            f"(e.g., HPHT_001 or Serum_MH_101). Got: {original_id}"
        )
        is_valid = False
    elif len(parts) == 2:
        # 2-part format: TYPE_INDEX
        type_text = parts[0]
        index = parts[1]
        researcher_initials = None  # Not present in 2-part format

        # Validate experiment type
        experiment_type = get_experiment_type_from_id(type_text)
        if not experiment_type:
            warnings.append(
                f"Unknown experiment type '{type_text}'. Expected one of: "
                f"{', '.join(sorted(set(EXPERIMENT_TYPE_ABBREVIATIONS.keys())))}"
            )

        # Validate index (should be numeric or alphanumeric)
        if not index:
            warnings.append("Index portion is missing (e.g., 001, 101)")

        is_valid = len(warnings) == 0
    else:
        # 3-part format: TYPE_INITIALS_INDEX
        type_text = parts[0]
        researcher_initials = parts[1]
        index = parts[2]

        # Validate experiment type
        experiment_type = get_experiment_type_from_id(type_text)
        if not experiment_type:
            warnings.append(
                f"Unknown experiment type '{type_text}'. Expected one of: "
                f"{', '.join(sorted(set(EXPERIMENT_TYPE_ABBREVIATIONS.keys())))}"
            )

        # Validate researcher initials (basic check)
        if not researcher_initials or not researcher_initials.isalnum():
            warnings.append(
                f"Researcher initials '{researcher_initials}' should be alphanumeric (e.g., MH, JD)"
            )

        # Validate index (should be numeric or alphanumeric)
        if not index:
            warnings.append("Index portion is missing (e.g., 101, 001)")

        is_valid = len(warnings) == 0

    return experiment_type, researcher_initials, index, is_valid, warnings


def parse_experiment_id_full(experiment_id: str) -> ParsedExperimentID:
    """
    Full canonical parse: replicate-grammar lineage fields plus base-stem
    classification and validity, in one ParsedExperimentID.

    Note: this uses the CANONICAL grammar (parse_lineage_fields). The legacy
    validation surface (backend.services.experiment_validation.parse_experiment_id)
    intentionally differs on two pinned shapes — combined "-N_Treatment"
    suffixes and naive trailing "-N" (e.g. CF-015). See that module.
    """
    if not experiment_id or not isinstance(experiment_id, str) or not experiment_id.strip():
        return ParsedExperimentID(
            experiment_type=None,
            researcher_initials=None,
            index=None,
            sequential_number=None,
            treatment_variant=None,
            base_id="",
            original_id=experiment_id if isinstance(experiment_id, str) else "",
            is_valid=False,
            warnings=["Experiment ID is empty or invalid"],
        )

    original_id = experiment_id.strip()
    base_id, sequential_number, treatment_variant, replicate_label = parse_lineage_fields(original_id)
    experiment_type, researcher_initials, index, is_valid, warnings = classify_base_id(base_id, original_id)

    return ParsedExperimentID(
        experiment_type=experiment_type,
        researcher_initials=researcher_initials,
        index=index,
        sequential_number=sequential_number,
        treatment_variant=treatment_variant,
        base_id=base_id,
        original_id=original_id,
        is_valid=is_valid,
        warnings=warnings,
        replicate_label=replicate_label,
    )
```

- [ ] **Step 4: Make `database/lineage_utils.py` delegate**

Replace lines 13-23 (the `import re`, `typing` imports, and the two module regexes) and the entire `parse_experiment_id` function body (lines 26-121) with:

```python
from typing import Optional, Tuple, TYPE_CHECKING
from sqlalchemy.orm import Session
from sqlalchemy import func

from .experiment_id_parser import parse_lineage_fields

if TYPE_CHECKING:
    from .models import Experiment


def parse_experiment_id(experiment_id: str) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[str]]:
    """
    Parse an experiment ID into (base_experiment_id, derivation_number,
    treatment_variant, replicate_label).

    Delegates to the canonical grammar in database/experiment_id_parser.py
    (issue #70 P5 consolidation) — see parse_lineage_fields there for the
    full delimiter rules and examples. Kept as a public wrapper because it
    is the 4-tuple surface used throughout lineage handling, event
    listeners, replicate routing, tests, and the data-migration script.
    """
    return parse_lineage_fields(experiment_id)
```

Notes for the implementer:
- Remove `import re` and the `_REPLICATE_LETTER_RE`/`_REPLICATE_GUARD_RE` definitions from `lineage_utils.py` **only after confirming** nothing else in the file uses them (as of the P5 branch point they are used only inside the old `parse_experiment_id` body). `re` is not used elsewhere in the file.
- Everything else in `lineage_utils.py` stays untouched in this task (Task 3 modifies `update_experiment_lineage`).
- Keep the module docstring at the top of `lineage_utils.py`; append one line noting the grammar now lives in `experiment_id_parser.py`.

- [ ] **Step 5: Run the new tests and the existing lineage pins**

Run: `.venv/Scripts/python -m pytest tests/test_experiment_id_parser.py tests/test_replicate_lineage.py tests/test_lineage_migration.py -q`
Expected: all PASS (existing pins prove the delegation is behavior-identical).

- [ ] **Step 6: Import smoke test (circular-import guard)**

Run: `.venv/Scripts/python -c "import database; from database import lineage_utils; from database import event_listeners; from backend.services import experiment_validation; from backend.services.bulk_uploads import replicate_routing, new_experiments; print('imports ok')"`
Expected: `imports ok`. If a circular import surfaces, move the `from database.models.enums import ExperimentType` import in `experiment_id_parser.py` inside `get_experiment_type_from_id`/`classify_base_id` (function-level) and re-run — do not restructure anything else.

- [ ] **Step 7: Run the broader affected suites**

Run: `.venv/Scripts/python -m pytest tests/test_experiment_rename.py tests/services/bulk_uploads/ tests/services/test_experiment_validation_replicates.py -q`
Expected: all PASS (0 failures).

- [ ] **Step 8: Commit**

```bash
git add database/experiment_id_parser.py database/lineage_utils.py tests/test_experiment_id_parser.py
git commit -m "[#70] Add canonical experiment ID parser module

- Grammar moved verbatim from lineage_utils.parse_experiment_id
- Classification extracted verbatim from experiment_validation
- lineage_utils.parse_experiment_id now delegates (same 4-tuple surface)
- Tests added: yes
- Docs updated: no"
```

---

### Task 2: experiment_validation delegates classification; divergences pinned

**Files:**
- Modify: `backend/services/experiment_validation.py` (imports, dataclass/type-map removal, `parse_experiment_id` body, `extract_lineage_info` docstring only)
- Modify: `tests/services/test_experiment_validation_replicates.py` (append one new class; change no existing lines)

**Interfaces:**
- Consumes (from Task 1): `database.experiment_id_parser.{ParsedExperimentID, classify_base_id, get_experiment_type_from_id, EXPERIMENT_TYPE_ABBREVIATIONS}`.
- Produces: `backend.services.experiment_validation.{parse_experiment_id, extract_lineage_info, validate_experiment_id, format_validation_warning, ParsedExperimentID, get_experiment_type_from_id, EXPERIMENT_TYPE_ABBREVIATIONS}` — all with byte-identical behavior to today. `new_experiments.py` (locked) and `legacy/streamlit_frontend/new_experiment.py` import from here and must need zero edits.

- [ ] **Step 1: Write the divergence-pinning tests FIRST and run them against the CURRENT code**

Append this class to `tests/services/test_experiment_validation_replicates.py` (do not modify any existing line):

```python
class TestLegacyLineageDivergencesPinned:
    """P5 (issue #70): extract_lineage_info is retained as a frozen legacy shim.

    Its algorithm diverges from the canonical grammar
    (database.experiment_id_parser.parse_lineage_fields) on two shapes, both of
    which are consumed by locked code (new_experiments.py's find_parent_for_copy
    and its parsed.sequential_number warning gate), so the divergent outputs are
    pinned here as KNOWN ISSUES rather than fixed. Do not "fix" these without an
    explicit product decision.
    """

    def test_naive_trailing_dash_number_cf_shape(self):
        # Canonical grammar: ("CF-015", None, None, None). Legacy: any trailing
        # -N is sequential, regardless of the prefix shape.
        assert extract_lineage_info("CF-015") == ("CF", 15, None, None)

    def test_naive_trailing_dash_number_hyphenated_shape(self):
        # Canonical grammar: ("TEST-SAMPLE-001", None, None, None).
        assert extract_lineage_info("TEST-SAMPLE-001") == ("TEST-SAMPLE", 1, None, None)

    def test_combined_suffix_bug_two_part(self):
        # Same pre-existing bug as test_existing_combined_unaffected, 2-part shape.
        # Canonical grammar: ("HPHT_001", 2, "Desorption", None).
        assert extract_lineage_info("HPHT_001-2_Desorption") == ("HPHT_001-2", None, "Desorption", None)

    def test_parsed_dataclass_pins_cf_shape(self):
        result = parse_experiment_id("CF-015")
        assert result.sequential_number == 15
        assert result.base_id == "CF"
        assert result.is_valid is False
        assert result.replicate_label is None

    def test_parsed_dataclass_pins_combined_shape(self):
        result = parse_experiment_id("Serum_MH_101-2_Desorption")
        assert result.sequential_number is None
        assert result.treatment_variant == "Desorption"
        assert result.base_id == "Serum_MH_101-2"
        assert result.index == "101-2"
        assert result.researcher_initials == "MH"
        assert result.is_valid is True

    def test_valid_id_warning_text_unchanged(self):
        # Warning strings surface verbatim in bulk-upload feedback; pin one.
        result = parse_experiment_id("XYZ_001")
        assert result.is_valid is False
        assert any("Unknown experiment type 'XYZ'" in w for w in result.warnings)
```

- [ ] **Step 2: Run the pins against the UNMODIFIED module — they must already pass**

Run: `.venv/Scripts/python -m pytest tests/services/test_experiment_validation_replicates.py -q`
Expected: all PASS. If any pin fails here, the pin itself is wrong — fix the test to match actual current behavior (never the code), and note it.

- [ ] **Step 3: Refactor `experiment_validation.py`**

Make exactly these changes:

1. Replace the module-level definitions of `EXPERIMENT_TYPE_ABBREVIATIONS` (lines 27-39), `ParsedExperimentID` (lines 42-54), and `get_experiment_type_from_id` (lines 57-79) with re-exports from the canonical module. The new import block at the top:

```python
from typing import Optional, Tuple, List
import re

from database.experiment_id_parser import (
    EXPERIMENT_TYPE_ABBREVIATIONS,
    ParsedExperimentID,
    classify_base_id,
    get_experiment_type_from_id,
)

__all__ = [
    "EXPERIMENT_TYPE_ABBREVIATIONS",
    "ParsedExperimentID",
    "get_experiment_type_from_id",
    "extract_lineage_info",
    "parse_experiment_id",
    "validate_experiment_id",
    "format_validation_warning",
]
```

(Remove the now-unused `from dataclasses import dataclass`, `Dict` from typing, and `from database.models.enums import ExperimentType` imports. `re` stays — `extract_lineage_info` uses it.)

2. `extract_lineage_info`: **do not touch the function body.** Replace the docstring with:

```python
    """
    LEGACY lineage extraction — frozen, pinned behavior (issue #70 P5).

    The canonical experiment ID grammar lives in
    database/experiment_id_parser.py::parse_lineage_fields. This function is
    retained verbatim because its algorithm diverges from the canonical
    grammar on shapes that locked callers depend on
    (backend/services/bulk_uploads/new_experiments.py::find_parent_for_copy
    and the parsed.sequential_number warning gate in the same file):

    1. Naive trailing "-N": ANY trailing hyphen-number is treated as a
       sequential number, so extract_lineage_info("CF-015") returns
       ("CF", 15, None, None) while the canonical grammar treats CF-015 as
       a standalone base experiment.
    2. Combined "-N_Treatment" suffixes (pre-existing bug, predates issue
       #69): the hyphen-NUMBER match requires the entire tail after the
       last hyphen to be purely digits, so the sequential number is never
       extracted and stays glued to base_id:
       extract_lineage_info("HPHT_001-2_Desorption") returns
       ("HPHT_001-2", None, "Desorption", None), NOT ("HPHT_001", 2, ...).

    Both divergences are pinned by
    tests/services/test_experiment_validation_replicates.py
    (TestLegacyLineageDivergencesPinned and test_existing_combined_unaffected).
    Do not modify this function's behavior without an explicit product
    decision covering every caller.

    Returns:
        Tuple of (base_id, sequential_number, treatment_variant, replicate_label)
    """
```

3. `parse_experiment_id`: keep the early-return branch for empty/non-string input exactly as-is (lines 225-236). Replace the classification section (lines 243-299, from `# Parse base_id - support both 2-part and 3-part formats` through the second `is_valid = len(warnings) == 0`) with a single call, so the function body becomes:

```python
    warnings = []

    if not experiment_id or not isinstance(experiment_id, str):
        return ParsedExperimentID(
            experiment_type=None,
            researcher_initials=None,
            index=None,
            sequential_number=None,
            treatment_variant=None,
            base_id="",
            original_id=experiment_id or "",
            is_valid=False,
            warnings=["Experiment ID is empty or invalid"]
        )

    original_id = experiment_id.strip()

    # Extract lineage info first — NOTE: intentionally the LEGACY extraction,
    # not the canonical grammar; see extract_lineage_info's docstring.
    base_id, sequential_number, treatment_variant, replicate_label = extract_lineage_info(original_id)

    # Classification (type / initials / index / validity) is shared with the
    # canonical parser module.
    experiment_type, researcher_initials, index, is_valid, warnings = classify_base_id(base_id, original_id)

    return ParsedExperimentID(
        experiment_type=experiment_type,
        researcher_initials=researcher_initials,
        index=index,
        sequential_number=sequential_number,
        treatment_variant=treatment_variant,
        base_id=base_id,
        original_id=original_id,
        is_valid=is_valid,
        warnings=warnings,
        replicate_label=replicate_label,
    )
```

Keep the existing function docstring; append one sentence: `Lineage fields use the legacy extraction (see extract_lineage_info); classification is shared with database/experiment_id_parser.py.`

4. In `extract_lineage_info`'s docstring Examples (if you keep the examples block alongside the new text above, which is preferred): correct the stale example — `extract_lineage_info("HPHT_001-2_Desorption")` actually returns `("HPHT_001-2", None, "Desorption", None)`, not `("HPHT_001", 2, "Desorption", None)`. All other examples are accurate and may be carried over verbatim.

5. `validate_experiment_id` and `format_validation_warning`: untouched.

- [ ] **Step 4: Run the validation suites**

Run: `.venv/Scripts/python -m pytest tests/services/test_experiment_validation_replicates.py tests/test_experiment_id_parser.py -q`
Expected: all PASS (pins prove byte-identical behavior through the refactor).

- [ ] **Step 5: Verify the locked callers need zero edits**

Run: `git diff --name-only` — must NOT list `backend/services/bulk_uploads/new_experiments.py` or `database/data_migrations/establish_experiment_lineage_006.py`.
Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/ tests/test_lineage_migration.py -q`
Expected: all PASS.
Run the import smoke test again: `.venv/Scripts/python -c "from backend.services.bulk_uploads import new_experiments; from legacy.streamlit_frontend import new_experiment" 2>&1 | tail -1` — the legacy streamlit import may fail on a missing `streamlit` package in this venv; if so, verify instead with `.venv/Scripts/python -c "from backend.services.experiment_validation import parse_experiment_id, validate_experiment_id, format_validation_warning, extract_lineage_info, get_experiment_type_from_id, ParsedExperimentID; print('surface ok')"`.
Expected: `surface ok`.

- [ ] **Step 6: Commit**

```bash
git add backend/services/experiment_validation.py tests/services/test_experiment_validation_replicates.py
git commit -m "[#70] Delegate validation parser to canonical module

- classify_base_id/type-map/dataclass now imported from experiment_id_parser
- extract_lineage_info frozen as documented legacy shim (2 divergences pinned)
- Zero edits to locked new_experiments.py / migration script (verified)
- Tests added: yes
- Docs updated: no"
```

---

### Task 3: Letter + sequential parent wiring (the one sanctioned behavior change)

**Files:**
- Modify: `database/lineage_utils.py::update_experiment_lineage` (the `if replicate_label is not None:` branch, currently lines 347-352)
- Modify: `tests/test_replicate_lineage.py` (append one new class; change no existing lines)

**Interfaces:**
- Consumes: `_find_experiment_by_exact_spelling(db, candidate_id)` and `find_replicate_group_parent(db, base_id)` — both existing in `lineage_utils.py`, both already `session.new`-aware (they resolve rows still pending in the current flush).
- Produces: new lineage behavior — an experiment parsing to `(base, N, None, letter)` (letter + sequential, **no treatment**) gets `parent_experiment_fk` = the lettered sibling `f"{base}{letter}"` when that row exists (in DB or pending in the same flush), else falls back to the current group-parent resolution. Locked interpretation of the issue: **any** `-N` on a lettered ID links to the letter itself (`SERUM_001a-3` → `SERUM_001a`, not `SERUM_001a-2`); letter+sequential+**treatment** combos (`SERUM_001a-2_Desorption`) keep today's group-parent linking.

- [ ] **Step 1: Write the failing tests**

Append this class to `tests/test_replicate_lineage.py` (reuse the existing `sqlite_session` fixture and `_make_exp` helper; do not modify any existing line — note `test_letter_plus_sequential_does_not_crash` in the existing class asserts only base/label, so it stays green through this change):

```python
class TestLetterSequentialParentWiring:
    """P5 (issue #70): SERUM_001a-2 links to SERUM_001a as parent.

    P1 parsed letter+sequential IDs but deliberately did not wire the parent;
    this is the one sanctioned behavior change in P5. Locked interpretation:
    any -N on a lettered ID links to the lettered sibling itself (a-3 -> a),
    and treatment combos keep the pre-P5 group-parent link.
    """

    def test_letter_seq_links_to_lettered_sibling(self, sqlite_session):
        stem = _make_exp(sqlite_session, "REP20_001", 920001)
        rep_a = _make_exp(sqlite_session, "REP20_001a", 920002)
        rerun = _make_exp(sqlite_session, "REP20_001a-2", 920003)
        assert rerun.parent_experiment_fk == rep_a.id
        assert rerun.parent_experiment_fk != stem.id
        assert rerun.base_experiment_id == "REP20_001"
        assert rerun.replicate_label == "a"

    def test_letter_seq_falls_back_to_group_parent_when_sibling_missing(self, sqlite_session):
        # Pre-P5 behavior pinned: without the lettered sibling, a-2 still
        # links to the group parent (stem), exactly as before.
        stem = _make_exp(sqlite_session, "REP21_001", 920010)
        rerun = _make_exp(sqlite_session, "REP21_001a-2", 920011)
        assert rerun.parent_experiment_fk == stem.id

    def test_letter_seq_orphan_when_nothing_exists(self, sqlite_session):
        rerun = _make_exp(sqlite_session, "REP22_001a-2", 920020)
        assert rerun.parent_experiment_fk is None
        assert rerun.base_experiment_id == "REP22_001"
        assert rerun.replicate_label == "a"

    def test_higher_seq_links_to_letter_itself_not_previous_rerun(self, sqlite_session):
        rep_a = _make_exp(sqlite_session, "REP23_001a", 920030)
        rerun2 = _make_exp(sqlite_session, "REP23_001a-2", 920031)
        rerun3 = _make_exp(sqlite_session, "REP23_001a-3", 920032)
        assert rerun2.parent_experiment_fk == rep_a.id
        assert rerun3.parent_experiment_fk == rep_a.id  # a-3 -> a, NOT a-2

    def test_same_flush_creation_wires_parent(self, sqlite_session):
        # The lettered sibling is pending in the SAME flush (no PK yet);
        # _find_experiment_by_exact_spelling's session.new scan must resolve it.
        rep_a = Experiment(
            experiment_id="REP24_001a", experiment_number=920040,
            status=ExperimentStatus.ONGOING, date=datetime.date(2026, 1, 1),
        )
        rerun = Experiment(
            experiment_id="REP24_001a-2", experiment_number=920041,
            status=ExperimentStatus.ONGOING, date=datetime.date(2026, 1, 1),
        )
        sqlite_session.add_all([rep_a, rerun])
        sqlite_session.flush()
        assert rep_a.id is not None
        assert rerun.parent_experiment_fk == rep_a.id

    def test_letter_seq_treatment_combo_keeps_group_parent(self, sqlite_session):
        # Pre-P5 behavior pinned: a treatment on a lettered re-run
        # (parses to base/seq/treatment/letter all set) is OUT of the
        # sanctioned wiring — it keeps linking to the group parent.
        stem = _make_exp(sqlite_session, "REP25_001", 920050)
        rep_a = _make_exp(sqlite_session, "REP25_001a", 920051)
        combo = _make_exp(sqlite_session, "REP25_001a-2_Desorption", 920052)
        assert combo.parent_experiment_fk == stem.id

    def test_plain_replicate_wiring_unchanged(self, sqlite_session):
        # Regression guard: plain lettered replicates (no -N) still link to
        # the group parent exactly as in P1.
        stem = _make_exp(sqlite_session, "REP26_001", 920060)
        rep_a = _make_exp(sqlite_session, "REP26_001a", 920061)
        assert rep_a.parent_experiment_fk == stem.id
```

- [ ] **Step 2: Run the new tests to verify the wiring ones fail**

Run: `.venv/Scripts/python -m pytest tests/test_replicate_lineage.py::TestLetterSequentialParentWiring -q`
Expected: `test_letter_seq_links_to_lettered_sibling`, `test_higher_seq_links_to_letter_itself_not_previous_rerun`, and `test_same_flush_creation_wires_parent` FAIL (they currently link to the stem / nothing); the fallback/orphan/treatment/plain tests PASS (they pin current behavior).

- [ ] **Step 3: Implement the wiring**

In `database/lineage_utils.py::update_experiment_lineage`, replace the current replicate branch:

```python
    if replicate_label is not None:
        parent = find_replicate_group_parent(db, base_id)
        # Assign via the relationship (not a raw `.id`): find_replicate_group_parent
        # can resolve a group-parent row that is itself still pending in the current
        # flush (no primary key yet) — see _find_experiment_by_exact_spelling.
        experiment.parent = parent
```

with:

```python
    if replicate_label is not None:
        parent = None
        if derivation_num is not None and treatment_variant is None:
            # P5 (issue #70): a sequential re-run of a lettered replicate
            # (e.g. SERUM_001a-2) links to the lettered sibling (SERUM_001a).
            # Any -N links to the letter itself (a-3 -> a, not a-2). Treatment
            # combos are excluded and keep the group-parent link below.
            parent = _find_experiment_by_exact_spelling(db, f"{base_id}{replicate_label}")
        if parent is None:
            # Plain replicate, or fallback when the lettered sibling doesn't
            # exist: pre-P5 group-parent resolution (bare stem, then -0, -1).
            parent = find_replicate_group_parent(db, base_id)
        # Assign via the relationship (not a raw `.id`): both resolvers can
        # return a row that is itself still pending in the current flush
        # (no primary key yet) — see _find_experiment_by_exact_spelling.
        experiment.parent = parent
```

Also update the "Classification" section of `update_experiment_lineage`'s docstring: change the replicate-member bullet to:

```
        - Replicate member (replicate_label set): base_experiment_id = stem. Parent:
          a letter+sequential re-run with no treatment (e.g. SERUM_001a-2) resolves
          to the lettered sibling (SERUM_001a) when it exists; otherwise (plain
          replicate, treatment combo, or sibling missing) the group parent via
          find_replicate_group_parent (bare stem, then -0, then -1).
```

No other function changes. Do **not** touch `get_or_find_parent_experiment`, `update_orphaned_derivations`, or `database/event_listeners.py` (the listener's `is_parent_row` bookkeeping is unaffected — lettered rows were never parent rows).

- [ ] **Step 4: Run the wiring tests and every suite that exercises lineage**

Run: `.venv/Scripts/python -m pytest tests/test_replicate_lineage.py tests/test_lineage_migration.py tests/test_experiment_rename.py tests/test_replicate_creation_service.py tests/services/bulk_uploads/ tests/api/test_experiments.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add database/lineage_utils.py tests/test_replicate_lineage.py
git commit -m "[#70] Wire letter+sequential replicate parent links

- SERUM_001a-2 -> parent SERUM_001a when the sibling exists (incl. same-flush)
- Fallback to group parent unchanged; treatment combos unchanged (pinned)
- Locked interpretation: a-3 -> a (letter itself), not a-2
- Tests added: yes
- Docs updated: no"
```

---

### Task 4: Documentation, decision log, full-suite verification

**Files:**
- Modify: `.claude/rules/MODELS.md` (Experiment → Lineage Tracking section)
- Modify: `docs/working/decisions.md` (append one entry)
- Modify: `docs/user_guide/REPLICATES.md` (one short paragraph)

**Interfaces:**
- Consumes: the shipped behavior from Tasks 1-3 (canonical module, frozen legacy shim, letter+sequential wiring).
- Produces: documentation only; no code.

- [ ] **Step 1: Update `.claude/rules/MODELS.md`**

In the `### Experiment` section, under **Lineage Tracking**, after the `replicate_label` bullet, add:

```markdown
  - **Parent wiring for letter + sequential re-runs (P5):** an ID like `SERUM_001a-2` (a sequential re-run of lettered replicate `a`) sets `parent_experiment_fk` to the lettered sibling `SERUM_001a` when that experiment exists (including when both are created in the same flush); otherwise it falls back to the group parent (bare stem, then `-0`, then `-1`), as before P5. Any `-N` links to the letter itself (`a-3` → `a`, not `a-2`). Letter + sequential + treatment combos (e.g. `SERUM_001a-2_Desorption`) are excluded and keep the group-parent link. Insertion-order caveat: if `a-2` is created while neither `a` nor the stem exists, it is orphaned; a later insert of the **stem** back-links it to the stem (the orphan pass is letter-unaware), and a later insert of `a` alone does not re-link it.
  - **Canonical ID parser:** the experiment ID grammar lives in `database/experiment_id_parser.py` (`parse_lineage_fields` / `parse_experiment_id_full`); `database/lineage_utils.py::parse_experiment_id` is a delegating wrapper. `backend/services/experiment_validation.py::extract_lineage_info` is a frozen **legacy** shim whose divergent behavior (naive trailing `-N`, e.g. `CF-015` → sequential 15 of `CF`; combined `-N_Treatment` suffixes never extract the sequential number) is deliberately pinned because locked bulk-upload code depends on it.
```

- [ ] **Step 2: Append to `docs/working/decisions.md`**

```markdown
## 2026-07-24 — Canonical experiment ID parser; extract_lineage_info frozen as legacy shim; a-N links to the letter itself

**Decision:** `database/experiment_id_parser.py` is the single source of truth for the experiment ID grammar (`parse_lineage_fields`, 4-tuple) and base-stem classification (`classify_base_id`), with `parse_experiment_id_full` returning the complete parse. `database/lineage_utils.py::parse_experiment_id` delegates to it. `backend/services/experiment_validation.py::extract_lineage_info` is retained **verbatim as a frozen legacy shim** — not collapsed — because its algorithm diverges from the canonical grammar on inputs that locked code consumes: (1) it treats ANY trailing `-N` as a sequential number (`CF-015` → `("CF", 15)`; canonical: standalone), which `new_experiments.py`'s `find_parent_for_copy` and its `parsed.sequential_number` warning gate depend on for real Core Flood IDs; (2) the pre-existing combined `-N_Treatment` bug (sequential never extracted) pinned since P1. Both divergences are pinned by `TestLegacyLineageDivergencesPinned`. Additionally, P5's sanctioned parent wiring is interpreted as: any `-N` on a lettered replicate links to the lettered sibling itself (`SERUM_001a-3` → `SERUM_001a`, not `SERUM_001a-2`), and letter+sequential+treatment combos keep the pre-P5 group-parent link.

**Why:** Issue #70 P5 mandated collapsing the two parsers onto one implementation with no behavior change, but the two parsers demand contradictory outputs for identical inputs (both pinned by pre-existing tests), so a literal collapse is impossible. Per the task briefing's pre-authorized default, current behavior was pinned and documented rather than changed.

**Scope:** New code needing an ID parse must use `database/experiment_id_parser.py` (or the `lineage_utils` 4-tuple wrapper) — never `extract_lineage_info`, which exists only for its two legacy consumers. Changing `extract_lineage_info`'s behavior requires an explicit product decision covering `find_parent_for_copy` and the bulk-upload warning gate. `get_or_find_parent_experiment` remains frozen for the data-migration script's sake (decision 2026-07-23).
```

- [ ] **Step 3: Update `docs/user_guide/REPLICATES.md`**

In the section describing replicate IDs/lineage (after the ID-format explanation), add:

```markdown
### Re-running a single replicate

If one vial of a replicate set is re-run, name it by appending a sequential number to the lettered ID (e.g. `SERUM_001a-2` for the second run of vial `a`). The re-run is linked to the lettered replicate itself (`SERUM_001a`) as its parent, so the lineage chain reads stem → `a` → `a-2`. If the lettered experiment does not exist in the system, the re-run falls back to linking directly to the group parent.
```

- [ ] **Step 4: Full backend suite**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: everything passes except exactly the 3 known pre-existing failures in `tests/test_pg_backup_restore.py` (local pg_dump toolchain gap) and 4 skips. Record the exact counts for the PR body.

- [ ] **Step 5: Verify reporting views recreate on import (issue #70 global acceptance)**

Run: `.venv/Scripts/python -c "import database.event_listeners; print('views ok')"`
Expected: `views ok` with no view-creation errors logged (P5 touches no views, but the global acceptance requires the check).

- [ ] **Step 6: Confirm zero-edit files stayed zero-edit**

Run: `git diff develop --name-only`
Expected list is exactly: `database/experiment_id_parser.py`, `database/lineage_utils.py`, `backend/services/experiment_validation.py`, `tests/test_experiment_id_parser.py`, `tests/services/test_experiment_validation_replicates.py`, `tests/test_replicate_lineage.py`, `.claude/rules/MODELS.md`, `docs/working/decisions.md`, `docs/user_guide/REPLICATES.md`, `docs/superpowers/plans/2026-07-24-issue-70-p5-parser-consolidation.md`, plus hook-synced copies under `docs/project_context/`. Any other file is a scope violation — investigate before committing.

- [ ] **Step 7: Commit**

```bash
git add .claude/rules/MODELS.md docs/working/decisions.md docs/user_guide/REPLICATES.md docs/project_context/
git commit -m "[#70] Document parser consolidation

- MODELS.md lineage + canonical-parser notes, REPLICATES.md re-run section
- decisions.md: frozen legacy shim + a-N -> a interpretation
- Tests added: no
- Docs updated: yes"
```

---

## Self-Review (completed at plan-writing time)

- **Spec coverage:** single parser module (Task 1) ✓; full parse with type/tag/index/replicate/sequential/treatment/base/validity (Task 1 `parse_experiment_id_full`) ✓; all callers updated — lineage_utils (Task 1), experiment_validation (Task 2), new_experiments.py and migration script (verified zero-edit-needed, Tasks 2/4 Step checks) ✓; letter+sequential wiring + tests (Task 3) ✓; previous parser tests pass unchanged (no existing test lines modified; every task runs them) ✓; combined-suffix bug pinned not fixed, flagged (header section + Task 2) ✓; full suite green with only the 3 known failures (Task 4) ✓.
- **Placeholder scan:** none — every step has complete code or exact commands.
- **Type consistency:** `parse_lineage_fields` / `classify_base_id` / `parse_experiment_id_full` / `ParsedExperimentID` names and signatures match across Tasks 1-3; `_find_experiment_by_exact_spelling` and `find_replicate_group_parent` consumed as-is from existing code.
