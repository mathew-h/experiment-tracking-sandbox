"""serum_vial_size_mL: nominal serum vial size on experimental_conditions
(docs/issues/issue-serum_vial_size.md.txt). Pins the column, the migration's
place in the chain, and that the migration's view SQL is the same view that
database/event_listeners.py recreates on API startup."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Integer

from database.models.conditions import ExperimentalConditions

REVISION = "e9a4c1f7b3d2"
PARENT = "b8c4e2d7f9a1"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _script_dir():
    return ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini")))


def _migration_module():
    path = REPO_ROOT / "alembic" / "versions" / f"{REVISION}_add_serum_vial_size_ml.py"
    spec = importlib.util.spec_from_file_location("_serum_vial_migration", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _norm(sql: str) -> str:
    return " ".join(sql.split())


def test_model_has_nullable_integer_column():
    col = ExperimentalConditions.__table__.columns["serum_vial_size_mL"]
    assert isinstance(col.type, Integer)
    assert col.nullable is True
    assert col.default is None and col.server_default is None


def test_alembic_has_a_single_head():
    # len()==1, not ==[REVISION], so the next migration doesn't break this test (E2/PR-D shape).
    assert len(_script_dir().get_heads()) == 1


def test_revision_revises_pr_d_drop():
    assert _script_dir().get_revision(REVISION).down_revision == PARENT


def test_migration_new_view_matches_startup_view():
    from database.event_listeners import _VIEWS

    mod = _migration_module()
    assert _norm(mod._V_CONDITIONS_NEW) == _norm(dict(_VIEWS)["v_experiment_conditions"])


def test_migration_old_view_is_new_view_minus_the_column():
    mod = _migration_module()
    assert 'ec."serum_vial_size_mL"' in mod._V_CONDITIONS_NEW
    assert 'serum_vial_size_mL' not in mod._V_CONDITIONS_OLD
    assert _norm(mod._V_CONDITIONS_NEW.replace('ec."serum_vial_size_mL",', "")) == _norm(
        mod._V_CONDITIONS_OLD
    )
