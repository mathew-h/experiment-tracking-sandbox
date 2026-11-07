"""Migration c6d2f8a4e1b9: experimental_conditions.reactor_series (issue #147)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import String

from database.models.conditions import ExperimentalConditions

REVISION = "c6d2f8a4e1b9"
PARENT = "b7e2d9c4a1f6"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _script_dir():
    return ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini")))


def _load(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "alembic" / "versions" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mod():
    return _load(f"{REVISION}_add_reactor_series_to_conditions.py", "_reactor_series_migration")


def _norm(sql: str) -> str:
    return " ".join(sql.split())


def test_column_shape():
    col = ExperimentalConditions.__table__.columns["reactor_series"]
    assert isinstance(col.type, String) and col.type.length == 4
    assert col.nullable is True and col.default is None and col.server_default is None


def test_check_constraint_on_model():
    names = {c.name for c in ExperimentalConditions.__table__.constraints}
    assert "ck_conditions_reactor_series" in names


def test_single_head():
    assert len(_script_dir().get_heads()) == 1


def test_revision_parent():
    assert _script_dir().get_revision(REVISION).down_revision == PARENT


def test_conditions_view_matches_startup():
    from database.event_listeners import _VIEWS

    assert _norm(_mod()._V_CONDITIONS_NEW) == _norm(dict(_VIEWS)["v_experiment_conditions"])


def test_old_view_is_new_minus_columns():
    mod = _mod()
    added = "ec.reactor_series, ec.reactor_slot, "
    assert "ec.reactor_number, " + added in _norm(mod._V_CONDITIONS_NEW)
    assert _norm(mod._V_CONDITIONS_NEW).replace(added, "") == _norm(mod._V_CONDITIONS_OLD)


def test_old_view_matches_predecessor():
    # downgrade() restores _V_CONDITIONS_OLD; it must be exactly what f3b7c2a9d4e1 created.
    prev = _load("f3b7c2a9d4e1_core_flood_columns_and_view.py", "_core_flood_migration_prev")
    assert _norm(prev._V_CONDITIONS_NEW) == _norm(_mod()._V_CONDITIONS_OLD)


def test_downgrade_restores_view_before_dropping_column():
    src = (REPO_ROOT / "alembic" / "versions" / f"{REVISION}_add_reactor_series_to_conditions.py").read_text()
    down = src[src.index("def downgrade"):]
    assert down.index("_V_CONDITIONS_OLD") < down.index("drop_column")
