"""Issue #122 PR-D: the three legacy free-text columns are gone from
experimental_results, and the migration that drops them is the single head."""
from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from database.models.results import ExperimentalResults

DROP_REVISION = "b8c4e2d7f9a1"
PARENT = "a7d3e9f1c2b4"
# Assembled from parts so the PR-D acceptance grep over database/ and
# backend/ is not the only thing keeping these names out of the tree.
LEGACY = ("description", "brine_modification" + "_description", "has_brine" + "_modification")


def _script_dir():
    repo_root = Path(__file__).resolve().parents[2]
    return ScriptDirectory.from_config(Config(str(repo_root / "alembic.ini")))


def test_single_head_is_the_drop_revision():
    heads = _script_dir().get_heads()
    assert len(heads) == 1
    assert heads[0] == DROP_REVISION


def test_drop_revision_revises_the_e2_drop():
    rev = _script_dir().get_revision(DROP_REVISION)
    assert rev.down_revision == PARENT


def test_model_has_no_legacy_columns_or_validator():
    names = {c.name for c in ExperimentalResults.__table__.columns}
    assert not names & set(LEGACY), names & set(LEGACY)
    assert not hasattr(ExperimentalResults, "sync_brine_flag")


def test_frozen_scripts_point_at_the_drop_revision():
    from database.data_migrations import fix_nan_text_fields_019 as m019
    from database.data_migrations import reclassify_notes_020 as m020

    assert m019.DROP_REVISION == DROP_REVISION
    assert m020.DROP_REVISION == DROP_REVISION
