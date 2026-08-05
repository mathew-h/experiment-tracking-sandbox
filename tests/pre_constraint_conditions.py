"""Simulate a database that predates uq_conditions_experiment_fk.

Migration 00063a5dd6a8 makes a second experimental_conditions row for one
experiment impossible going forward. But the readers fixed in issue #109 must
still degrade rather than 500 on a database restored from a backup taken before
the cleanup ran, and the 018 cleanup script exists precisely to remove such
rows -- so a handful of tests must be able to create the anomaly. They are the
only place a duplicate is created deliberately.

Why the constraint has to be dropped at all: tests/api/conftest.py's
session-scoped fixture and two tests/models/ module fixtures drop_all +
create_all the shared experiments_test schema from live ORM metadata, so any
mid-run rebuild bakes the constraint in. Keeping it out of that database by
omission is not possible.

Two designs were tried and rejected before this one, both confirmed by actually
running the affected suites (not by inspection alone):

1. DROP/ADD issued via `session.commit()` / `session.rollback()` directly on
   the caller's own session. Three of the nine wrapped tests use
   `tests/data_migrations/conftest.py::migration_session`, whose whole point is
   a `session.begin_nested()` SAVEPOINT so an internal `db.commit()` (the
   migration functions under test) releases only the savepoint, never the real
   outer transaction. This helper's own `session.commit()` releases that same
   savepoint the same way, popping the session onto its *parent* transaction;
   the later `session.rollback()` then rolls back that real outer transaction,
   undoing the DROP along with it, so the following `ADD CONSTRAINT` collides
   with the constraint the rollback just resurrected
   (`psycopg2.errors.DuplicateTable` on `uq_conditions_experiment_fk`).
2. DROP/ADD issued on a *separate* connection (`engine.begin()`), to sidestep
   the caller's transaction bookkeeping entirely. This avoids problem 1 but
   self-deadlocks: the caller's own session has, by the time `finally` runs,
   already read `experimental_conditions` in its still-open transaction (that
   is the whole point of these tests) and holds a lock on it; a *second*
   connection's `ALTER TABLE ... ADD CONSTRAINT` needs an ACCESS EXCLUSIVE lock
   on the same table and blocks waiting for the first connection to finish --
   which it never does, because the single-threaded test is itself blocked
   waiting for the ALTER to return. Confirmed by hanging
   `pytest tests/data_migrations/test_dedupe_conditions_018.py` past its
   timeout with two backends visible in `pg_stat_activity`, one `idle in
   transaction` holding the lock and one `active`/`Lock` waiting on it.

The actual fix: stay on the caller's own session/connection (so there is only
ever one lock holder, never two) and never call `session.commit()` /
`session.rollback()` ourselves. `Session.in_nested_transaction()` tells us
whether we're riding a SAVEPOINT (`migration_session`) or a plain transaction
(`db_session` / `db`):
- Nested: do nothing extra. The DROP, the test's own rows, and this helper's
  own DEDUPE/ADD in `finally` all live in the same still-open savepoint: when
  `migration_session`'s `outer_transaction.rollback()` fires at teardown, all
  of it -- DROP included -- is undone together, which correctly restores
  whatever state preceded the test.
- Not nested: several of these tests call `.commit()` themselves mid-test (or
  reach a router that does), which durably drops the constraint for real. We
  must durably restore it the same way, so `finally` calls `session.commit()`
  once DEDUPE has removed the surplus rows the test created (`ADD CONSTRAINT`
  would otherwise fail on them).
"""
from contextlib import contextmanager

from sqlalchemy import text

CONSTRAINT = "uq_conditions_experiment_fk"

_DROP = f"ALTER TABLE experimental_conditions DROP CONSTRAINT IF EXISTS {CONSTRAINT}"
_ADD = (
    f"ALTER TABLE experimental_conditions "
    f"ADD CONSTRAINT {CONSTRAINT} UNIQUE (experiment_fk)"
)
_DEDUPE = """
    DELETE FROM experimental_conditions ec
    WHERE ec.id > (
        SELECT MIN(x.id) FROM experimental_conditions x
        WHERE x.experiment_fk = ec.experiment_fk
    )
"""


@contextmanager
def without_conditions_unique(session):
    """Drop uq_conditions_experiment_fk for the duration of one test, on the
    caller's own session -- never a separate connection. See module
    docstring for why (deadlock) and for the nested-transaction handling.
    """
    session.execute(text(_DROP))
    try:
        yield
    finally:
        session.execute(text(_DEDUPE))
        session.execute(text(_ADD))
        if not session.in_nested_transaction():
            session.commit()
