"""Tests for replicate-letter support in experiment ID lineage parsing (issue #69)."""
import pytest

from database.lineage_utils import parse_experiment_id


class TestParseExperimentIdReplicateGrammar:
    """4-tuple (base_experiment_id, derivation_num, treatment_variant, replicate_label)."""

    def test_bare_stem(self):
        assert parse_experiment_id("SERUM_001") == ("SERUM_001", None, None, None)

    def test_explicit_parent_dash_0(self):
        assert parse_experiment_id("SERUM_001-0") == ("SERUM_001", 0, None, None)

    def test_explicit_parent_dash_1(self):
        assert parse_experiment_id("SERUM_001-1") == ("SERUM_001", 1, None, None)

    def test_replicate_letter_two_part(self):
        assert parse_experiment_id("SERUM_001a") == ("SERUM_001", None, None, "a")

    def test_replicate_letter_three_part(self):
        assert parse_experiment_id("Serum_MH_101a") == ("Serum_MH_101", None, None, "a")

    def test_replicate_letter_does_not_degrade_to_treatment(self):
        # Regression guard: must NOT parse as base="Serum_MH", treatment="101a"
        result = parse_experiment_id("Serum_MH_101a")
        assert result[0] == "Serum_MH_101"
        assert result[2] is None

    def test_replicate_letter_plus_sequential(self):
        assert parse_experiment_id("SERUM_001a-2") == ("SERUM_001", 2, None, "a")

    def test_type_prefixed_id_unaffected(self):
        assert parse_experiment_id("CF-015") == ("CF-015", None, None, None)

    def test_existing_sequential_unaffected(self):
        assert parse_experiment_id("HPHT_MH_001-2") == ("HPHT_MH_001", 2, None, None)

    def test_existing_treatment_unaffected(self):
        assert parse_experiment_id("HPHT_MH_001_Desorption") == ("HPHT_MH_001", None, "Desorption", None)

    def test_existing_combined_sequential_treatment_unaffected(self):
        assert parse_experiment_id("HPHT_MH_001-2_Desorption") == ("HPHT_MH_001", 2, "Desorption", None)

    def test_empty_and_none(self):
        assert parse_experiment_id("") == (None, None, None, None)
        assert parse_experiment_id(None) == (None, None, None, None)
        assert parse_experiment_id("   ") == (None, None, None, None)


import os
import sys
import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import Base
from database.models import Experiment
from database.models.enums import ExperimentStatus
from database.lineage_utils import update_experiment_lineage, find_replicate_group_parent


@pytest.fixture
def sqlite_session():
    """In-memory SQLite session with JSONB columns patched to JSON (SQLite has no JSONB)."""
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    original_types = {}
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                original_types[(table.name, col.name)] = col.type
                col.type = JSON()

    engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        for table in Base.metadata.tables.values():
            for col in table.columns:
                key = (table.name, col.name)
                if key in original_types:
                    col.type = original_types[key]


def _make_exp(session, experiment_id, number, replicate_label=None):
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=number,
        status=ExperimentStatus.ONGOING,
        date=datetime.date(2026, 1, 1),
    )
    session.add(exp)
    session.flush()  # before_flush listener sets base_experiment_id/parent_experiment_fk/replicate_label
    return exp


class TestReplicateLineageWiring:
    def test_replicate_gets_base_and_label_no_parent_yet(self, sqlite_session):
        rep_a = _make_exp(sqlite_session, "REP1_001a", 910001)
        assert rep_a.base_experiment_id == "REP1_001"
        assert rep_a.replicate_label == "a"
        assert rep_a.parent_experiment_fk is None

    def test_replicate_links_to_existing_bare_stem_parent(self, sqlite_session):
        parent = _make_exp(sqlite_session, "REP2_001", 910010)
        rep_a = _make_exp(sqlite_session, "REP2_001a", 910011)
        rep_b = _make_exp(sqlite_session, "REP2_001b", 910012)
        assert rep_a.parent_experiment_fk == parent.id
        assert rep_b.parent_experiment_fk == parent.id
        assert parent.base_experiment_id == "REP2_001"
        assert parent.parent_experiment_fk is None

    def test_replicate_links_to_existing_dash0_parent(self, sqlite_session):
        parent = _make_exp(sqlite_session, "REP3_001-0", 910020)
        rep_a = _make_exp(sqlite_session, "REP3_001a", 910021)
        assert parent.base_experiment_id == "REP3_001"
        assert parent.parent_experiment_fk is None
        assert rep_a.parent_experiment_fk == parent.id

    def test_replicate_links_to_existing_dash1_parent(self, sqlite_session):
        parent = _make_exp(sqlite_session, "REP4_001-1", 910030)
        rep_a = _make_exp(sqlite_session, "REP4_001a", 910031)
        assert parent.base_experiment_id == "REP4_001"
        assert parent.parent_experiment_fk is None
        assert rep_a.parent_experiment_fk == parent.id

    def test_bare_stem_takes_precedence_over_dash1(self, sqlite_session):
        dash1_parent = _make_exp(sqlite_session, "REP5_001-1", 910040)
        bare_parent = _make_exp(sqlite_session, "REP5_001", 910041)
        rep_a = _make_exp(sqlite_session, "REP5_001a", 910042)
        assert rep_a.parent_experiment_fk == bare_parent.id
        assert rep_a.parent_experiment_fk != dash1_parent.id

    def test_orphan_replicates_backlink_when_bare_stem_parent_created_later(self, sqlite_session):
        rep_a = _make_exp(sqlite_session, "REP6_001a", 910050)
        rep_b = _make_exp(sqlite_session, "REP6_001b", 910051)
        assert rep_a.parent_experiment_fk is None
        assert rep_b.parent_experiment_fk is None

        parent = _make_exp(sqlite_session, "REP6_001", 910052)

        assert rep_a.parent_experiment_fk == parent.id
        assert rep_b.parent_experiment_fk == parent.id

    def test_orphan_replicates_backlink_when_dash0_parent_created_later(self, sqlite_session):
        rep_a = _make_exp(sqlite_session, "REP7_001a", 910060)
        assert rep_a.parent_experiment_fk is None

        parent = _make_exp(sqlite_session, "REP7_001-0", 910061)

        assert rep_a.parent_experiment_fk == parent.id

    def test_letter_plus_sequential_does_not_crash(self, sqlite_session):
        rep_a2 = _make_exp(sqlite_session, "REP8_001a-2", 910070)
        assert rep_a2.base_experiment_id == "REP8_001"
        assert rep_a2.replicate_label == "a"

    def test_dash0_row_is_a_parent_row_not_a_child(self, sqlite_session):
        parent = _make_exp(sqlite_session, "REP9_001-0", 910080)
        assert parent.base_experiment_id == "REP9_001"
        assert parent.parent_experiment_fk is None
        assert parent.replicate_label is None

    def test_find_replicate_group_parent_precedence(self, sqlite_session):
        bare = _make_exp(sqlite_session, "REP10_001", 910090)
        found = find_replicate_group_parent(sqlite_session, "REP10_001")
        assert found is not None
        assert found.id == bare.id

    def test_other_parent_alias_not_relinked_when_bare_stem_created_later(self, sqlite_session):
        """Regression guard: when both a '-1' parent-alias and (later) the bare stem
        exist, resolving the bare stem as the winning parent must NOT back-link the
        '-1' row as if it were an orphaned child — it is a parent alias, not a child."""
        dash1_parent = _make_exp(sqlite_session, "REP11_001-1", 910100)
        assert dash1_parent.parent_experiment_fk is None

        bare_parent = _make_exp(sqlite_session, "REP11_001", 910101)

        assert dash1_parent.parent_experiment_fk is None, (
            "a '-1' parent-alias row must never be back-linked to the bare-stem parent"
        )
        assert bare_parent.parent_experiment_fk is None
