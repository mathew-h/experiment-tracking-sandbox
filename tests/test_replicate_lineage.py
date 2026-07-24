"""Tests for replicate-letter support in experiment ID lineage parsing (issue #69)."""
import os
import sys
import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import Base
from database.models import Experiment
from database.models.enums import ExperimentStatus
from database.lineage_utils import parse_experiment_id, find_replicate_group_parent


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
