"""Unit tests for the issue #98 timepoint-stem collapse key."""
from __future__ import annotations

from sqlalchemy import func, literal, select

from database.experiment_id_parser import split_timepoint_token
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment
from backend.services.replicate_collapse import (
    TIMEPOINT_TOKEN_SQL_PATTERN,
    collapse_by_stem,
    timepoint_stem_expr,
)

# IDs spanning every shape the grammar produces. Used by both the SQL test and
# the Python-agreement test so the two implementations cannot drift (D1).
STEM_CASES = [
    ("SERUM_001a-t1", "SERUM_001a"),
    ("SERUM_001a-t3", "SERUM_001a"),
    ("SERUM_001a-t0.5", "SERUM_001a"),
    ("SERUM_001a-t0", "SERUM_001a"),
    ("SERUM_001a", "SERUM_001a"),      # no token -> unchanged
    ("SERUM_001", "SERUM_001"),
    ("SERUM_001-t7", "SERUM_001"),     # letterless -t vial
    ("SERUM_001a-2", "SERUM_001a-2"),  # sequential re-run: NOT a timepoint
    ("CF-015", "CF-015"),              # trailing -NNN is not a token
    ("SERUM_001a_Desorption", "SERUM_001a_Desorption"),
    ("SERUM_001a-T7", "SERUM_001a-T7"),  # uppercase T is not the token
]


def timepoint_stem_expr_literal(experiment_id: str):
    """timepoint_stem_expr applied to a literal, so the agreement test does not
    depend on the ID grammar accepting every case above as a real row."""
    return func.regexp_replace(literal(experiment_id), TIMEPOINT_TOKEN_SQL_PATTERN, "")


def _add(db, experiment_id: str, number: int, **kw) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
        **kw,
    )
    db.add(exp)
    return exp


class TestTimepointStemExpr:
    def test_sql_strips_the_token_against_real_rows(self, db_session):
        """The expression applied to an actual column, not a literal."""
        rows = [
            ("SERUM_801a-t1", "SERUM_801a"),
            ("SERUM_802a", "SERUM_802a"),
            ("SERUM_803a-2", "SERUM_803a-2"),
        ]
        for i, (experiment_id, _) in enumerate(rows):
            _add(db_session, experiment_id, 8100 + i)
        db_session.commit()
        got = dict(db_session.execute(
            select(Experiment.experiment_id, timepoint_stem_expr(Experiment))
            .where(Experiment.experiment_id.in_([r[0] for r in rows]))
        ).all())
        # Unconditional: every row must be present and correct.
        assert got == dict(rows)

    def test_sql_and_python_agree(self, db_session):
        """The POSIX pattern and split_timepoint_token must never diverge."""
        for experiment_id, expected in STEM_CASES:
            sql_stem = db_session.execute(
                select(timepoint_stem_expr_literal(experiment_id))
            ).scalar_one()
            py_stem, _ = split_timepoint_token(experiment_id)
            assert sql_stem == py_stem == expected, experiment_id

    def test_pattern_is_anchored(self):
        assert TIMEPOINT_TOKEN_SQL_PATTERN.endswith("$")


class TestCollapseByStem:
    def test_groups_timepoint_vials_and_keeps_rerun_separate(self, db_session):
        a = _add(db_session, "RC2_001a", 8200, replicate_label="a")
        a_t1 = _add(db_session, "RC2_001a-t1", 8201, replicate_label="a", id_timepoint_days=1.0)
        a_2 = _add(db_session, "RC2_001a-2", 8202, replicate_label="a")
        db_session.commit()

        groups = collapse_by_stem([a, a_t1, a_2])

        assert [g.stem for g in groups] == ["RC2_001a", "RC2_001a-2"]
        assert groups[0].vial_count == 2
        assert groups[1].vial_count == 1

    def test_representative_prefers_clean_earliest_vial(self, db_session):
        """is_outlier leads the ordering (D7), then timepoint NULLS FIRST."""
        outlier = _add(db_session, "RC3_001a-t1", 8300, replicate_label="a",
                       id_timepoint_days=1.0, is_outlier=True)
        clean = _add(db_session, "RC3_001a-t3", 8301, replicate_label="a",
                     id_timepoint_days=3.0)
        db_session.commit()

        (group,) = collapse_by_stem([outlier, clean])

        assert group.representative.experiment_id == "RC3_001a-t3"
        assert group.vial_count == 2

    def test_null_timepoint_sorts_before_a_day_value(self, db_session):
        bare = _add(db_session, "RC4_001a", 8400, replicate_label="a")
        t0 = _add(db_session, "RC4_001a-t0", 8401, replicate_label="a", id_timepoint_days=0.0)
        db_session.commit()

        (group,) = collapse_by_stem([t0, bare])

        assert group.representative.experiment_id == "RC4_001a"

    def test_empty_input(self):
        assert collapse_by_stem([]) == []
