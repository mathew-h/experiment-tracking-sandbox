"""Core flood permeability flow rate column (issue #140): one nullable Float on
experimental_results, the migration's place in the chain, and that its view SQL
is the same SQL database/event_listeners.py recreates on API startup."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Float

from database.event_listeners import _VIEWS
from database.models.results import ExperimentalResults

REVISION = "a1c5e8f2b9d3"
PARENT = "f3b7c2a9d4e1"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _script_dir():
    return ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini")))


def _load_migration(filename: str, module_name: str):
    path = REPO_ROOT / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _norm(sql: str) -> str:
    return " ".join(sql.split())


mod = _load_migration(f"{REVISION}_core_flood_permeability_flow_rate.py", "_core_flood_permeability_migration")
prev = _load_migration("f3b7c2a9d4e1_core_flood_columns_and_view.py", "_core_flood_columns_migration")


def test_permeability_column_nullable_float():
    col = ExperimentalResults.__table__.columns["permeability_flow_rate_mL_min"]
    assert isinstance(col.type, Float) and col.nullable is True
    assert col.default is None and col.server_default is None


def test_revision_parent():
    assert _script_dir().get_revision(REVISION).down_revision == PARENT


def test_single_head():
    assert len(_script_dir().get_heads()) == 1


def test_view_matches_startup():
    assert _norm(mod._V_CORE_FLOOD_SAMPLES) == _norm(dict(_VIEWS)["v_core_flood_samples"])


def test_old_view_is_predecessor():
    assert _norm(mod._V_CORE_FLOOD_SAMPLES_OLD) == _norm(prev._V_CORE_FLOOD_SAMPLES)


def test_new_view_is_old_plus_column():
    col = 'er."permeability_flow_rate_mL_min",'
    assert mod._V_CORE_FLOOD_SAMPLES.count('"permeability_flow_rate_mL_min"') == 2
    assert _norm(
        mod._V_CORE_FLOOD_SAMPLES.replace(col, "").replace('"permeability_flow_rate_mL_min",', "")
    ) == _norm(mod._V_CORE_FLOOD_SAMPLES_OLD)
