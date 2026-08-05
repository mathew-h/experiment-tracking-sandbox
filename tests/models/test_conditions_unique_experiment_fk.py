"""ExperimentalConditions is 1:1 with Experiment. Before issue #109 that was
assumed by the list endpoint, the delete snapshot and the Power BI views, and
enforced nowhere -- one duplicate row 500'd the experiments page, duplicated the
v_experiments dimension key and blocked deletion.

This file only checks that the UniqueConstraint is declared on the ORM model.
DB-level enforcement (that a second experimental_conditions row for the same
experiment_fk actually raises IntegrityError) is verified on a *fresh* database
in tests/test_fresh_install_migration.py, not here.

`experiments_test` (the DB the db_session fixture in tests/models/conftest.py
points at) deliberately does NOT carry this constraint: Base.metadata.create_all
never ALTERs an already-existing table, and four tests elsewhere in the suite
(tests/api/test_experiments.py::test_list_experiments_survives_duplicate_conditions,
tests/api/test_experiments.py::test_get_experiment_survives_duplicate_conditions,
tests/services/test_experiment_deletion.py::test_delete_succeeds_with_two_conditions_rows,
tests/services/bulk_uploads/test_experiment_deletion_bulk.py::
test_duplicate_conditions_row_does_not_block_bulk_delete) deliberately seed a
second conditions row for one experiment to prove the tolerant readers degrade
gracefully instead of 500ing. Adding the constraint to experiments_test would
break those tests and defeat their purpose.
"""
from database.models.conditions import ExperimentalConditions


def test_constraint_is_declared_on_the_model():
    names = {
        c.name for c in ExperimentalConditions.__table__.constraints if c.name
    }
    assert "uq_conditions_experiment_fk" in names
