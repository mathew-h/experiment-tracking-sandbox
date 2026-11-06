"""H2BackgroundLink (issue #144): table shape, CHECK/UNIQUE constraints, and the
migration's place in the chain (downgrade must drop dependent views first)."""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.exc import IntegrityError

from database.models import H2BackgroundLink

REVISION = "b7e2d9c4a1f6"
PARENT = "a1c5e8f2b9d3"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _script_dir():
    return ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini")))


def _load_migration():
    path = REPO_ROOT / "alembic" / "versions" / f"{REVISION}_h2_background_links.py"
    spec = importlib.util.spec_from_file_location("_h2_background_links_migration", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_revision_parent():
    assert _script_dir().get_revision(REVISION).down_revision == PARENT


def test_single_head():
    assert len(_script_dir().get_heads()) == 1


def test_columns():
    t = H2BackgroundLink.__table__
    assert t.name == "h2_background_links"
    assert t.c.id.primary_key
    assert t.c.base_experiment_id.nullable is False
    assert t.c.base_experiment_id.unique is True
    for name in ("background_base_id", "background_stem_id", "created_by"):
        assert t.c[name].nullable is True
    for name in ("created_at", "updated_at"):
        assert t.c[name].server_default is not None
        assert t.c[name].type.timezone is True
    assert t.c.updated_at.onupdate is not None


def test_one_ref_check(db_session):
    db_session.add(H2BackgroundLink(base_experiment_id="S1"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    db_session.add(H2BackgroundLink(
        base_experiment_id="S1", background_base_id="B1", background_stem_id="B1a"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_not_self_check(db_session):
    db_session.add(H2BackgroundLink(base_experiment_id="S1", background_base_id="S1"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_unique_base(db_session):
    db_session.add(H2BackgroundLink(base_experiment_id="S1", background_base_id="B1"))
    db_session.flush()
    db_session.add(H2BackgroundLink(base_experiment_id="S1", background_stem_id="B2a"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_downgrade_drops_views_first():
    src = inspect.getsource(_load_migration().downgrade)
    rollup = src.index("DROP VIEW IF EXISTS v_results_h2_bkg_adjusted_rollup")
    adjusted = src.index("DROP VIEW IF EXISTS v_results_h2_bkg_adjusted\"")
    drop = src.index("drop_table")
    assert rollup < adjusted < drop
