"""The 019 cleanup is frozen (issue #122 PR-D): the columns it cleaned were
dropped by Alembic b8c4e2d7f9a1. It must refuse to run with a message that
says so."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from database.data_migrations.fix_nan_text_fields_019 import (
    DROP_REVISION,
    LAST_RUNNABLE_COMMIT,
    MIGRATION_PATH,
    refuse_to_run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_refuses_to_run(migration_session):
    with pytest.raises(RuntimeError) as excinfo:
        refuse_to_run(migration_session)
    msg = str(excinfo.value)
    assert DROP_REVISION in msg
    assert f"git show {LAST_RUNNABLE_COMMIT}:{MIGRATION_PATH}" in msg
    assert "legacy columns are" in msg


def test_direct_invocation_prints_the_frozen_message_and_exits_3():
    cp = subprocess.run(
        [sys.executable, "-I", "database/data_migrations/fix_nan_text_fields_019.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert cp.returncode == 3, (cp.returncode, cp.stdout, cp.stderr)
    assert "Error: fix_nan_text_fields_019 is frozen" in cp.stderr
