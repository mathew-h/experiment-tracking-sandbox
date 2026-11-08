"""experiments.is_background and migration e4b9c2d7a6f1 (issue #152).

The column, the migration's place in the chain, view parity with the startup
_VIEWS (this is now the newest migration touching the four views), chain
parity with the previous definition of v_experiments, and the order of the
upgrade/downgrade SQL (views must be restored before the column is dropped).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from database.models import Experiment

REVISION = "e4b9c2d7a6f1"
PARENT = "d8a3f5c1e7b2"
REPO_ROOT = Path(__file__).resolve().parents[2]
VIEW_CONSTS = {
    "v_experiments": "_V_EXPERIMENTS",
    "v_results_scalar_rollup": "_V_SCALAR_ROLLUP",
    "v_results_h2_bkg_adjusted": "_V_H2_BKG_ADJUSTED",
    "v_results_h2_bkg_adjusted_rollup": "_V_H2_BKG_ADJUSTED_ROLLUP",
}


def _script_dir():
    return ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini")))


def _load(name: str):
    path = REPO_ROOT / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(f"_mig_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mod():
    return _load(f"{REVISION}_add_is_background_to_experiments.py")


def _norm(sql: str) -> str:
    return " ".join(sql.split())


def test_revision_parent():
    assert _script_dir().get_revision(REVISION).down_revision == PARENT


def test_single_head():
    assert len(_script_dir().get_heads()) == 1


@pytest.mark.parametrize("view", sorted(VIEW_CONSTS))
def test_new_view_matches_startup(view):
    from database.event_listeners import _VIEWS

    new = getattr(_mod(), VIEW_CONSTS[view] + "_NEW")
    assert _norm(new) == _norm(dict(_VIEWS)[view])
    assert "is_background" in new


@pytest.mark.parametrize("view", sorted(VIEW_CONSTS))
def test_old_view_predates_the_column(view):
    old = getattr(_mod(), VIEW_CONSTS[view] + "_OLD")
    assert f"CREATE VIEW {view} AS" in _norm(old)
    assert "is_background" not in old


def test_v_experiments_chain_parity():
    # c4d8f1a2b6e7 was the last migration to define v_experiments.
    prev = _load("c4d8f1a2b6e7_typed_notes_reporting_views.py")
    assert _norm(prev._V_EXPERIMENTS_NEW) == _norm(_mod()._V_EXPERIMENTS_OLD)


def test_new_columns_are_last():
    mod = _mod()
    assert _norm(mod._V_EXPERIMENTS_NEW).endswith(
        "e.is_background FROM experiments e LEFT JOIN experimental_conditions ec ON ec.experiment_fk = e.id")
    assert "AS is_background_group FROM experimental_results er" in _norm(mod._V_SCALAR_ROLLUP_NEW)


def test_upgrade_and_downgrade_sql_order(monkeypatch):
    mod = _mod()
    calls: list[str] = []
    monkeypatch.setattr(mod.op, "execute", lambda sql: calls.append(_norm(sql)))
    monkeypatch.setattr(mod.op, "add_column", lambda table, col: calls.append(f"ADD {table}.{col.name}"))
    monkeypatch.setattr(mod.op, "drop_column", lambda table, col: calls.append(f"DROP {table}.{col}"))

    mod.upgrade()
    assert calls[0] == "ADD experiments.is_background"
    drops = [c for c in calls if c.startswith("DROP VIEW")]
    assert drops[0] == "DROP VIEW IF EXISTS v_results_h2_bkg_adjusted_rollup"
    creates = [c.split(" AS")[0] for c in calls if c.startswith("CREATE VIEW")]
    assert creates.index("CREATE VIEW v_results_h2_bkg_adjusted") < creates.index(
        "CREATE VIEW v_results_h2_bkg_adjusted_rollup")

    calls.clear()
    mod.downgrade()
    assert calls[-1] == "DROP experiments.is_background"
    assert all("is_background" not in c for c in calls[:-1] if c.startswith("CREATE VIEW"))


def test_defaults_to_false(db_session):
    exp = Experiment(experiment_id="BKG_COL_001", experiment_number=915001)
    db_session.add(exp)
    db_session.flush()
    db_session.refresh(exp)
    assert exp.is_background is False


def test_server_default_and_not_null(db_session):
    db_session.execute(text(
        "INSERT INTO experiments (experiment_id, experiment_number) VALUES ('BKG_COL_002', 915002)"))
    assert db_session.execute(text(
        "SELECT is_background FROM experiments WHERE experiment_id = 'BKG_COL_002'")).scalar() is False
    with pytest.raises(IntegrityError):
        db_session.execute(text(
            "UPDATE experiments SET is_background = NULL WHERE experiment_id = 'BKG_COL_002'"))
        db_session.flush()
