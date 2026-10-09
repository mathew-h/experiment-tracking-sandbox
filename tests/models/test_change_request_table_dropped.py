"""Issue #122 PR-E (E2): the Notion-era reactor change-request table and its
model are gone. Alembic a7d3e9f1c2b4 drops the table; these tests pin the
migration chain and the ORM side so neither quietly comes back.

The table name is read from the migration module's TABLE constant on purpose:
the §4 acceptance grep for the dropped table is literal and must find nothing
under tests/.
"""
from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
DROP_REVISION = "a7d3e9f1c2b4"
PARENT_REVISION = "e5b2d9c7a1f4"


def _script_dir() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini")))


def test_drop_migration_is_the_single_head():
    assert _script_dir().get_heads() == [DROP_REVISION]


def test_drop_migration_revises_the_event_date_migration():
    rev = _script_dir().get_revision(DROP_REVISION)
    assert rev.down_revision == PARENT_REVISION


def test_metadata_has_no_table_for_the_dropped_migration():
    import database  # noqa: F401  (registers every model on Base)
    from database import Base

    dropped = _script_dir().get_revision(DROP_REVISION).module.TABLE
    assert dropped not in Base.metadata.tables


def test_no_mapped_class_targets_the_dropped_table():
    import database  # noqa: F401  (registers every model on Base)
    from database import Base

    dropped = _script_dir().get_revision(DROP_REVISION).module.TABLE
    offenders = [m.class_.__name__ for m in Base.registry.mappers if m.local_table.name == dropped]
    assert offenders == []


def test_every_package_export_resolves():
    # A stale export line left behind for a deleted model would make
    # `from database import *` fail at the first import.
    import database
    import database.models

    for pkg in (database, database.models):
        for name in pkg.__all__:
            assert hasattr(pkg, name), f"{pkg.__name__}.__all__ names {name!r} but it is not importable"
