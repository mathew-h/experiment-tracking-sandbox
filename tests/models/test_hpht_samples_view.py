"""Migration d8a3f5c1e7b2: the v_hpht_samples reporting view (issue #149).

Its place in the chain, that its view SQL is the same SQL
database/event_listeners.py recreates on API startup, and that downgrade
drops only the view.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REVISION = "d8a3f5c1e7b2"
PARENT = "c6d2f8a4e1b9"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _script_dir():
    return ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini")))


def _mod():
    path = REPO_ROOT / "alembic" / "versions" / f"{REVISION}_add_hpht_samples_view.py"
    spec = importlib.util.spec_from_file_location("_hpht_samples_migration", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _norm(sql: str) -> str:
    return " ".join(sql.split())


def test_revision_parent():
    assert _script_dir().get_revision(REVISION).down_revision == PARENT


def test_single_head():
    # #152's e4b9c2d7a6f1 follows this revision; only one head may exist.
    assert len(_script_dir().get_heads()) == 1


def test_view_matches_startup():
    from database.event_listeners import _VIEWS

    assert _norm(_mod()._V_HPHT_SAMPLES) == _norm(dict(_VIEWS)["v_hpht_samples"])


def test_upgrade_drops_before_create_and_downgrade_drops_view_only(monkeypatch):
    mod = _mod()
    calls: list[str] = []
    monkeypatch.setattr(mod.op, "execute", lambda sql: calls.append(_norm(sql)))
    mod.upgrade()
    assert calls[0] == "DROP VIEW IF EXISTS v_hpht_samples CASCADE"
    assert calls[1].startswith("CREATE VIEW v_hpht_samples AS")
    calls.clear()
    mod.downgrade()
    assert calls == ["DROP VIEW IF EXISTS v_hpht_samples CASCADE"]
