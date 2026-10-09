"""The 021 backfill is frozen (issue #122 PR-E E2). Its source table was
dropped by Alembic a7d3e9f1c2b4 after the production run of 2026-10-09
(357 rows, 331 converted, 26 orphaned). The script stays as the record of where
the 'migrate_change_requests_021' notes came from and must REFUSE to run with
a message that says so -- never crash on a missing table."""
from __future__ import annotations

import pytest

from database.data_migrations.migrate_reactor_change_requests_021 import (
    DROP_REVISION,
    LAST_RUNNABLE_COMMIT,
    MIGRATION_PATH,
    SOURCE_TAG,
    refuse_to_run,
)


def test_source_tag_is_pinned():
    # .claude/rules/MODELS.md, v_notes.created_by on 331 production rows and the
    # review-queue filter all cite this exact value; it must never drift.
    assert SOURCE_TAG == "migrate_change_requests_021"


def test_drop_revision_exists_in_the_alembic_chain():
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    repo_root = Path(__file__).resolve().parents[2]
    rev = ScriptDirectory.from_config(Config(str(repo_root / "alembic.ini"))).get_revision(DROP_REVISION)
    assert rev is not None
    assert rev.down_revision == "e5b2d9c7a1f4"


def test_refuses_when_the_source_table_is_gone(migration_session):
    # experiments_test is built by create_all from the post-E2 metadata, so the
    # source table does not exist here -- exactly the lab PC's state after the
    # nightly `alembic upgrade head`.
    with pytest.raises(RuntimeError) as excinfo:
        refuse_to_run(migration_session)
    msg = str(excinfo.value)
    assert DROP_REVISION in msg
    assert "2026-10-09" in msg
    assert "331" in msg and "26" in msg
    assert f"git show {LAST_RUNNABLE_COMMIT}:{MIGRATION_PATH}" in msg
