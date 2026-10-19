"""v_experiment_conditions exposes serum_vial_size_mL to Power BI; v_experiments
deliberately does not (docs/issues/issue-serum_vial_size.md.txt, settled decision 3)."""
from database.event_listeners import _VIEWS


def test_v_experiment_conditions_selects_serum_vial_size():
    sql = dict(_VIEWS)["v_experiment_conditions"]
    assert 'ec."serum_vial_size_mL"' in sql


def test_v_experiments_does_not_select_serum_vial_size():
    assert "serum_vial_size_mL" not in dict(_VIEWS)["v_experiments"]
