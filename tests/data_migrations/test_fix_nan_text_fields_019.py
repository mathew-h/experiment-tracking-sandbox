"""The 019 cleanup is frozen (issue #122 PR-D): the columns it cleaned were
dropped by Alembic b8c4e2d7f9a1. It must refuse to run with a message that
says so."""
from __future__ import annotations

import pytest

from database.data_migrations.fix_nan_text_fields_019 import (
    DROP_REVISION,
    LAST_RUNNABLE_COMMIT,
    MIGRATION_PATH,
    refuse_to_run,
)


def test_refuses_to_run(migration_session):
    with pytest.raises(RuntimeError) as excinfo:
        refuse_to_run(migration_session)
    msg = str(excinfo.value)
    assert DROP_REVISION in msg
    assert f"git show {LAST_RUNNABLE_COMMIT}:{MIGRATION_PATH}" in msg
    assert "legacy columns are" in msg
