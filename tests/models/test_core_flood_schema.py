"""Core flood schema (issue #132): per-sample tube/flow/pressure columns on
experimental_results and pore_volume_mL on experimental_conditions. Pins the
columns, the migration's place in the chain, and that the migration's view SQL
is the same SQL database/event_listeners.py recreates on API startup."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Float, Integer

from database.models.conditions import ExperimentalConditions
from database.models.results import ExperimentalResults

REVISION = "f3b7c2a9d4e1"
PARENT = "e9a4c1f7b3d2"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _script_dir():
    return ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini")))


def _migration_module():
    path = REPO_ROOT / "alembic" / "versions" / f"{REVISION}_core_flood_columns_and_view.py"
    spec = importlib.util.spec_from_file_location("_core_flood_migration", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _norm(sql: str) -> str:
    return " ".join(sql.split())


def test_new_columns_nullable():
    cols = ExperimentalResults.__table__.columns
    assert isinstance(cols["sample_tube_number"].type, Integer)
    for name in (
        "flow_rate_mL_min",
        "nitrogen_flow_rate_mL_min",
        "inlet_pressure_psi",
        "outlet_pressure_psi",
    ):
        assert isinstance(cols[name].type, Float), name
    # Pore pressure is experimental_conditions.pore_pressure, not a per-sample column.
    assert "pore_pressure_psi" not in cols

    pv = ExperimentalConditions.__table__.columns["pore_volume_mL"]
    assert isinstance(pv.type, Float)

    for col in [cols[n] for n in (
        "sample_tube_number", "flow_rate_mL_min", "nitrogen_flow_rate_mL_min",
        "inlet_pressure_psi", "outlet_pressure_psi",
    )] + [pv]:
        assert col.nullable is True, col.name
        assert col.default is None and col.server_default is None, col.name


def test_single_head():
    assert len(_script_dir().get_heads()) == 1


def test_revision_parent():
    assert _script_dir().get_revision(REVISION).down_revision == PARENT


def test_dim_and_conditions_views_match_startup():
    from database.event_listeners import _VIEWS

    mod = _migration_module()
    views = dict(_VIEWS)
    assert _norm(mod._V_DIM_NEW) == _norm(views["v_dim_timepoints"])
    assert _norm(mod._V_CONDITIONS_NEW) == _norm(views["v_experiment_conditions"])


def test_old_views_are_new_minus_column():
    mod = _migration_module()
    assert "er.sample_tube_number," in mod._V_DIM_NEW
    assert 'ec."pore_volume_mL",' in mod._V_CONDITIONS_NEW
    assert "sample_tube_number" not in mod._V_DIM_OLD
    assert "pore_volume_mL" not in mod._V_CONDITIONS_OLD
    assert _norm(mod._V_DIM_NEW.replace("er.sample_tube_number,", "")) == _norm(mod._V_DIM_OLD)
    assert _norm(mod._V_CONDITIONS_NEW.replace('ec."pore_volume_mL",', "")) == _norm(
        mod._V_CONDITIONS_OLD
    )
