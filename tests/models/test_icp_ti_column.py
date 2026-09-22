"""Tests for the ICPResults.ti (Titanium) column and the single-source-of-truth
contract for the ICP fixed-element list.

The contract tests exist because the fixed-element list has drifted three times
(2026-01 sr..tl, 2026-05 ag..v, 2026-06 s): a column was added to the model, but
one or more of the mirrors -- the Pydantic schema, the upload router's runtime
stub, the test stub -- was not, so readings landed in ``all_elements`` only or
were dropped from API responses.
"""
import datetime

from sqlalchemy import Float

from backend.api.schemas.results import ICP_ELEMENTS, ICPCreate
from database.models import Experiment, ExperimentalResults, ICPResults

# Float columns on icp_results that are NOT element concentrations.
_NON_ELEMENT_FLOATS = {"dilution_factor"}


def _model_element_columns() -> set[str]:
    return {
        c.name for c in ICPResults.__table__.columns
        if isinstance(c.type, Float) and c.name not in _NON_ELEMENT_FLOATS
    }


def test_ti_column_stores_and_reads_back(db_session):
    exp = Experiment(
        experiment_id="TI_COL_001",
        experiment_number=920001,
        status="ONGOING",
        date=datetime.date(2026, 1, 1),
    )
    db_session.add(exp)
    db_session.flush()
    er = ExperimentalResults(
        experiment_fk=exp.id,
        time_post_reaction_days=1.0,
        time_post_reaction_bucket_days=1.0,
        is_primary_timepoint_result=True,
        description="Day 1 results",
    )
    db_session.add(er)
    db_session.flush()
    icp = ICPResults(result_id=er.id, ti=0.11, all_elements={"ti": 0.11})
    db_session.add(icp)
    db_session.flush()
    db_session.expire(icp)
    assert icp.ti == 0.11
    assert icp.get_element_concentration("Ti") == 0.11


def test_ti_defaults_to_null():
    assert ICPResults.__table__.columns["ti"].nullable is True
    assert isinstance(ICPResults.__table__.columns["ti"].type, Float)


def test_icp_elements_matches_model_columns():
    """ICP_ELEMENTS is the canonical list the upload router and test stub use."""
    assert set(ICP_ELEMENTS) == _model_element_columns()
    assert len(ICP_ELEMENTS) == len(set(ICP_ELEMENTS)), "duplicate in ICP_ELEMENTS"


def test_icp_create_schema_exposes_every_element():
    """ICPResponse inherits ICPCreate with from_attributes, so a column missing
    here is silently dropped from every API response (the 2026-08-13 Na/V bug)."""
    missing = set(ICP_ELEMENTS) - set(ICPCreate.model_fields)
    assert not missing, f"ICPCreate is missing element fields: {sorted(missing)}"


def test_v_results_icp_exposes_every_element_but_s():
    """Every fixed element is a *_ppm column in the Power BI view. `s_ppm` is a
    known pre-existing gap (2026-08-13) and is exempted here on purpose; delete
    the exemption when it is fixed."""
    from database.event_listeners import _VIEWS

    sql = dict(_VIEWS)["v_results_icp"]
    missing = {el for el in ICP_ELEMENTS if f"AS {el}_ppm" not in sql} - {"s"}
    assert not missing, f"v_results_icp is missing: {sorted(missing)}"
    assert "icp.ti   AS ti_ppm" in sql
