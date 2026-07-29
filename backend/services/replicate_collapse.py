"""Timepoint-vial collapsing (issue #98).

A sacrificial-timepoint vial differs from its siblings ONLY by the trailing
'-t<days>' token (issue #81): SERUM_001a, SERUM_001a-t1 and SERUM_001a-t3 are
the same logical replicate sampled at different times. Collapsing rows that
differ solely by that token is what lets the Experiments list show replicate
identity instead of one row per destroyed vial.

The collapse key is the experiment_id with the token stripped -- the "stem".
It is deliberately NOT (base_experiment_id, replicate_label):
parse_lineage_fields("SERUM_001a-2") returns ("SERUM_001", 2, None, "a"), so a
sequential re-run of a lettered replicate shares BOTH base and letter with
SERUM_001a and would be wrongly merged into it. There is no persisted
derivation-number column to separate them. See decision D1 in
docs/superpowers/specs/2026-07-29-issue-98-t-vial-replicate-collapsing-design.md.

PATTERN DUPLICATION -- the '-t<days>' pattern exists in three places and they
must stay aligned. tests/services/test_replicate_collapse.py::
TestTimepointStemExpr::test_sql_and_python_agree is the guard:
  1. database/experiment_id_parser.py::_TIMEPOINT_TOKEN_RE  (canonical, Python)
  2. frontend/src/utils/experimentId.ts::TIMEPOINT_TOKEN_RE  (TypeScript)
  3. TIMEPOINT_TOKEN_SQL_PATTERN below                       (POSIX, for Postgres)
Python-side stripping always reuses (1) via split_timepoint_token -- never add
a fourth copy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import func

from database.experiment_id_parser import split_timepoint_token
from database.models.experiments import Experiment

# POSIX-ERE equivalent of database/experiment_id_parser.py::_TIMEPOINT_TOKEN_RE:
# '-t' + digits + an optional decimal part, anchored to end-of-string. Lowercase
# 't' only. Anchoring means regexp_replace can match at most once, so its
# replace-first-only default is what we want.
TIMEPOINT_TOKEN_SQL_PATTERN = r"-t[0-9]+(\.[0-9]+)?$"


def timepoint_stem_expr(col):
    """SQL expression: `experiment_id` with a trailing '-t<days>' token stripped.

    A no-op for IDs without the token, so this is safe to apply unconditionally.

    `col` is either the ``Experiment`` class or a subquery's ``.c`` collection,
    matching the ``_bucket_key_expr(col)`` convention in
    ``backend/api/routers/experiments.py``.
    """
    return func.regexp_replace(col.experiment_id, TIMEPOINT_TOKEN_SQL_PATTERN, "")


@dataclass
class StemGroup:
    """Rows sharing one timepoint-stripped experiment_id."""
    stem: str
    representative: Experiment
    vial_count: int


def _representative_sort_key(exp: Experiment):
    """Clean vials before flagged ones (D7), then earliest timepoint with NULL
    first (a bare vial precedes its own -t vials), then lowest number."""
    return (
        bool(exp.is_outlier),
        exp.id_timepoint_days is not None,
        exp.id_timepoint_days if exp.id_timepoint_days is not None else 0.0,
        exp.experiment_number,
    )


def collapse_by_stem(rows: Sequence[Experiment]) -> list[StemGroup]:
    """Group rows by stem, preserving first-appearance order of the stems.

    Each group's `representative` is chosen by _representative_sort_key, so it
    is the earliest non-outlier vial. `vial_count` is the number of rows the
    group stands for.
    """
    buckets: dict[str, list[Experiment]] = {}
    order: list[str] = []
    for row in rows:
        stem, _days = split_timepoint_token(row.experiment_id)
        if stem not in buckets:
            buckets[stem] = []
            order.append(stem)
        buckets[stem].append(row)
    return [
        StemGroup(
            stem=stem,
            representative=min(buckets[stem], key=_representative_sort_key),
            vial_count=len(buckets[stem]),
        )
        for stem in order
    ]
