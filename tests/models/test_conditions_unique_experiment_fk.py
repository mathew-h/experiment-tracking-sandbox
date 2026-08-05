"""ExperimentalConditions is 1:1 with Experiment. Before issue #109 that was
assumed by the list endpoint, the delete snapshot and the Power BI views, and
enforced nowhere -- one duplicate row 500'd the experiments page, duplicated the
v_experiments dimension key and blocked deletion.

This file only checks that the UniqueConstraint is declared on the ORM model.
DB-level enforcement (that a second experimental_conditions row for the same
experiment_fk actually raises IntegrityError) is verified on a *fresh* scratch
database in tests/test_fresh_install_migration.py, not here -- `experiments_test`
is long-lived, so a one-off DB-level check here would depend on that database's
history rather than the migration itself.

`experiments_test` is NOT reliably free of this constraint. tests/api/conftest.py's
session-scoped fixture and two tests/models/ module fixtures (drop_all +
create_all against live ORM metadata) bake the constraint into that database on
any mid-run rebuild, so it can appear there depending on run order. Nine tests
elsewhere in the suite deliberately seed a second conditions row for one
experiment to prove the tolerant readers degrade gracefully instead of 500ing,
and each wraps its body in tests/pre_constraint_conditions.py::
without_conditions_unique(session) to drop the constraint for the duration of
that `with` block (see that module's docstring for why a plain
commit/rollback or a second connection don't work):
- tests/api/test_experiments.py::test_list_experiments_survives_duplicate_conditions
- tests/api/test_experiments.py::test_get_experiment_survives_duplicate_conditions
- tests/data_migrations/test_dedupe_conditions_018.py (five call sites)
- tests/services/test_experiment_deletion.py::test_delete_succeeds_with_two_conditions_rows
- tests/services/bulk_uploads/test_experiment_deletion_bulk.py::
  test_duplicate_conditions_row_does_not_block_bulk_delete

A tenth test that needs to seed a duplicate must use the same helper.
"""
from database.models.conditions import ExperimentalConditions


def test_constraint_is_declared_on_the_model():
    names = {
        c.name for c in ExperimentalConditions.__table__.constraints if c.name
    }
    assert "uq_conditions_experiment_fk" in names
