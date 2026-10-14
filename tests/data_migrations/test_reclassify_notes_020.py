"""The 020 backfill is frozen (issue #122 PR-D). The two legacy result columns it
read were dropped by Alembic b8c4e2d7f9a1 after the production apply; the script
stays as the record of its rules (its docstring) and of where the
'reclassify_notes_020' notes came from, and must REFUSE to run with a message
that says so -- never crash on a missing column."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from database.data_migrations.reclassify_notes_020 import (
    DROP_REVISION,
    LAST_RUNNABLE_COMMIT,
    MIGRATION_PATH,
    SOURCE_TAG,
    refuse_to_run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_source_tag_is_pinned():
    # v_notes.created_by on the backfilled rows and MODELS.md cite this value.
    assert SOURCE_TAG == "reclassify_notes_020"


def test_refuses_to_run(migration_session):
    with pytest.raises(RuntimeError) as excinfo:
        refuse_to_run(migration_session)
    msg = str(excinfo.value)
    assert DROP_REVISION in msg
    assert "issue #122 PR-D" in msg
    assert f"git show {LAST_RUNNABLE_COMMIT}:{MIGRATION_PATH}" in msg
    assert "legacy columns are" in msg


def test_direct_invocation_prints_the_frozen_message_and_exits_3():
    cp = subprocess.run(
        [sys.executable, "-I", "database/data_migrations/reclassify_notes_020.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert cp.returncode == 3, (cp.returncode, cp.stdout, cp.stderr)
    assert "Error: reclassify_notes_020 is frozen" in cp.stderr
