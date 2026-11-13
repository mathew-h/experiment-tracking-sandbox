"""Issue #190 (backend sweep PR 2): shared router helpers."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.api.routers._helpers import call_or_http


class _Base(Exception):
    pass


class _Missing(_Base):
    pass


def _raise(exc: Exception):
    raise exc


def test_call_or_http_returns_the_value():
    assert call_or_http(lambda: 7, ((_Base, 422),)) == 7


def test_call_or_http_maps_the_first_matching_type():
    """A subclass listed before its base wins; the base still maps the rest."""
    errors = ((_Missing, 404), (_Base, 422))
    with pytest.raises(HTTPException) as missing:
        call_or_http(lambda: _raise(_Missing("gone")), errors)
    assert (missing.value.status_code, missing.value.detail) == (404, "gone")
    with pytest.raises(HTTPException) as invalid:
        call_or_http(lambda: _raise(_Base("bad")), errors)
    assert (invalid.value.status_code, invalid.value.detail) == (422, "bad")


def test_call_or_http_lets_an_unlisted_exception_through():
    with pytest.raises(KeyError):
        call_or_http(lambda: _raise(KeyError("x")), ((_Base, 422),))


def test_call_or_http_uses_the_detail_builder():
    with pytest.raises(HTTPException) as exc:
        call_or_http(lambda: _raise(_Missing("HPHT_1")), ((_Missing, 404),),
                     detail=lambda e: f"No run {e}")
    assert exc.value.detail == "No run HPHT_1"


# ── experiment lookups (D-01) ────────────────────────────────────────────────

def _exp(db_session, experiment_id: str, number: int, base: str | None = None):
    from database.models.enums import ExperimentStatus
    from database.models.experiments import Experiment

    exp = Experiment(experiment_id=experiment_id, experiment_number=number,
                     base_experiment_id=base, status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.flush()
    return exp


def test_find_experiment_matches_the_exact_id_only(db_session):
    from backend.services.experiment_lookup import find_experiment

    exp = _exp(db_session, "LOOKUP190_001", 9190001)
    assert find_experiment(db_session, "LOOKUP190_001") is exp
    # Exact match: no case folding or zero stripping (that is _id_match's job).
    assert find_experiment(db_session, "lookup190_001") is None
    assert find_experiment(db_session, "LOOKUP190_1") is None


def test_get_experiment_or_404_returns_the_row_or_raises(db_session):
    from backend.api.routers._helpers import get_experiment_or_404

    exp = _exp(db_session, "LOOKUP190_002", 9190002)
    assert get_experiment_or_404(db_session, "LOOKUP190_002") is exp
    with pytest.raises(HTTPException) as default:
        get_experiment_or_404(db_session, "LOOKUP190_NOPE")
    assert (default.value.status_code, default.value.detail) == (404, "Experiment not found")
    with pytest.raises(HTTPException) as custom:
        get_experiment_or_404(db_session, "LOOKUP190_NOPE", detail="Experiment conditions not found")
    assert custom.value.detail == "Experiment conditions not found"


def test_series_key_is_the_base_id_else_the_own_id(db_session):
    from backend.services.experiment_lookup import series_key

    assert series_key(_exp(db_session, "LOOKUP190_003-2", 9190003, base="LOOKUP190_003")) == "LOOKUP190_003"
    assert series_key(_exp(db_session, "LOOKUP190_004", 9190004)) == "LOOKUP190_004"


# ── conditions and scalar lookups (D-02, D-05) ───────────────────────────────

def _conditions(db_session, exp, **fields):
    from database.models.conditions import ExperimentalConditions

    cond = ExperimentalConditions(experiment_fk=exp.id, experiment_id=exp.experiment_id, **fields)
    db_session.add(cond)
    db_session.flush()
    return cond


def test_lowest_conditions_returns_the_row_or_none(db_session):
    from backend.services.experiment_lookup import lowest_conditions

    with_row = _exp(db_session, "LOOKUP190_010", 9190010)
    without = _exp(db_session, "LOOKUP190_011", 9190011)
    cond = _conditions(db_session, with_row, rock_mass_g=2.0)
    assert lowest_conditions(db_session, with_row.id) is cond
    assert lowest_conditions(db_session, without.id) is None


def test_lowest_conditions_map_keys_by_experiment_and_skips_the_missing(db_session):
    from backend.services.experiment_lookup import lowest_conditions_map

    a = _exp(db_session, "LOOKUP190_012", 9190012)
    b = _exp(db_session, "LOOKUP190_013", 9190013)
    bare = _exp(db_session, "LOOKUP190_014", 9190014)
    cond_a, cond_b = _conditions(db_session, a), _conditions(db_session, b)
    assert lowest_conditions_map(db_session, [a.id, b.id, bare.id]) == {a.id: cond_a, b.id: cond_b}
    assert lowest_conditions_map(db_session, []) == {}


# ── run helpers (D-15, D-16) ─────────────────────────────────────────────────

def test_is_variant_is_true_only_for_parent_underscore_text(db_session):
    from backend.services.experiment_lookup import is_variant

    root = _exp(db_session, "LOOKUP190_020", 9190020, base="LOOKUP190_020")
    segment = _exp(db_session, "LOOKUP190_020-2", 9190021, base="LOOKUP190_020")
    bypass = _exp(db_session, "LOOKUP190_020-2_Bypass1", 9190022, base="LOOKUP190_020")
    lookalike = _exp(db_session, "LOOKUP190_020-25", 9190023, base="LOOKUP190_020")
    segment.parent, bypass.parent, lookalike.parent = root, segment, segment
    db_session.flush()

    assert is_variant(root) is False        # no parent
    assert is_variant(segment) is False     # sequential: <parent>-2
    assert is_variant(bypass) is True       # side sample: <parent>_Bypass1
    assert is_variant(lookalike) is False   # shares a prefix, no underscore


def test_root_description_prefers_the_first_root_then_the_first_described():
    from types import SimpleNamespace as Row

    from backend.services.run_service import root_description

    def is_root(m):
        return m.root

    described_root = [Row(root=False, description="side"), Row(root=True, description="root text")]
    assert root_description(described_root, is_root) == "root text"
    blank_root = [Row(root=True, description=None), Row(root=False, description="fallback")]
    assert root_description(blank_root, is_root) == "fallback"
    two_roots = [Row(root=True, description="first"), Row(root=True, description="second")]
    assert root_description(two_roots, is_root) == "first"
    assert root_description([Row(root=False, description=None)], is_root) is None
    assert root_description([], is_root) is None
