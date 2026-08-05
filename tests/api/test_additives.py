from __future__ import annotations
import pytest
from database.models.experiments import Experiment, ModificationsLog
from database.models.conditions import ExperimentalConditions
from database.models.chemicals import Compound, ChemicalAdditive
from database.models.enums import ExperimentStatus, AmountUnit
from sqlalchemy import select


@pytest.fixture(autouse=True)
def _cleanup_addstale_rows(db_session):
    """Item 1 (issue #109) regression tests below commit real rows into the
    shared experiments_test database. Clean up everything prefixed ADDSTALE_
    so it cannot leak into later test files. Modeled on
    tests/api/test_conditions.py:12-28.
    """
    yield
    db_session.query(ExperimentalConditions).filter(
        ExperimentalConditions.experiment_id.like("ADDSTALE_%")
    ).delete(synchronize_session=False)
    db_session.query(Experiment).filter(
        Experiment.experiment_id.like("ADDSTALE_%")
    ).delete(synchronize_session=False)
    db_session.query(Compound).filter(
        Compound.name.like("ADDSTALE_%")
    ).delete(synchronize_session=False)
    db_session.commit()


def _setup_experiment_with_additive(db, exp_id="ADDTEST_001", number=6001,
                                     compound_name="Iron Oxide", amount=5.0, unit=AmountUnit.GRAM):
    exp = Experiment(experiment_id=exp_id, experiment_number=number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    cond = ExperimentalConditions(
        experiment_id=exp_id,
        experiment_fk=exp.id,
        rock_mass_g=100.0,
        water_volume_mL=500.0,
    )
    db.add(cond)
    db.flush()
    compound = Compound(name=compound_name, molecular_weight_g_mol=159.69)
    db.add(compound)
    db.flush()
    additive = ChemicalAdditive(
        experiment_id=cond.id,
        compound_id=compound.id,
        amount=amount,
        unit=unit,
    )
    db.add(additive)
    db.commit()
    db.refresh(additive)
    db.refresh(compound)
    db.refresh(exp)
    return exp, cond, compound, additive


# ── PATCH /api/additives/{additive_id} ────────────────────────────────────────

def test_patch_additive_amount(client, db_session):
    exp, cond, compound, additive = _setup_experiment_with_additive(db_session)
    resp = client.patch(f"/api/additives/{additive.id}", json={"amount": 10.0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["amount"] == 10.0
    assert body["unit"] == "g"  # unchanged


def test_patch_additive_unit(client, db_session):
    _, _, _, additive = _setup_experiment_with_additive(db_session, "ADDTEST_002", 6002)
    resp = client.patch(f"/api/additives/{additive.id}", json={"unit": "mg"})
    assert resp.status_code == 200
    assert resp.json()["unit"] == "mg"


def test_patch_additive_compound(client, db_session):
    exp, cond, compound, additive = _setup_experiment_with_additive(db_session, "ADDTEST_003", 6003)
    new_compound = Compound(name="Silica", molecular_weight_g_mol=60.08)
    db_session.add(new_compound)
    db_session.commit()
    resp = client.patch(f"/api/additives/{additive.id}", json={"compound_id": new_compound.id})
    assert resp.status_code == 200
    assert resp.json()["compound_id"] == new_compound.id


def test_patch_additive_invalid_unit_returns_422(client, db_session):
    _, _, _, additive = _setup_experiment_with_additive(db_session, "ADDTEST_004", 6004)
    resp = client.patch(f"/api/additives/{additive.id}", json={"unit": "furlongs"})
    assert resp.status_code == 422


def test_patch_additive_not_found_returns_404(client):
    resp = client.patch("/api/additives/99999", json={"amount": 1.0})
    assert resp.status_code == 404


def test_patch_additive_writes_modifications_log(client, db_session):
    exp, cond, compound, additive = _setup_experiment_with_additive(db_session, "ADDTEST_005", 6005)
    client.patch(f"/api/additives/{additive.id}", json={"amount": 20.0})
    log_entry = db_session.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_fk == exp.id,
            ModificationsLog.modified_table == "chemical_additives",
            ModificationsLog.modification_type == "update",
        )
    ).scalar_one_or_none()
    assert log_entry is not None
    assert log_entry.old_values == {"amount": 5.0}
    assert log_entry.new_values == {"amount": 20.0}


def test_patch_additive_recalculates_moles(client, db_session):
    """After changing amount, moles_added must reflect the new amount."""
    _, _, _, additive = _setup_experiment_with_additive(
        db_session, "ADDTEST_006", 6006, compound_name="FeO_calc", amount=159.69, unit=AmountUnit.GRAM
    )
    resp = client.patch(f"/api/additives/{additive.id}", json={"amount": 319.38})
    assert resp.status_code == 200
    # molecular_weight = 159.69 g/mol, amount = 319.38 g → 2.0 mol
    body = resp.json()
    assert body["moles_added"] is not None
    assert abs(body["moles_added"] - 2.0) < 0.01


def test_patch_additive_duplicate_compound_returns_409(client, db_session):
    """Changing compound_id to one already in the experiment violates unique constraint."""
    exp, cond, compound_a, additive_a = _setup_experiment_with_additive(
        db_session, "ADDTEST_007", 6007, compound_name="CompA_409"
    )
    compound_b = Compound(name="CompB_409", molecular_weight_g_mol=50.0)
    db_session.add(compound_b)
    db_session.flush()
    additive_b = ChemicalAdditive(
        experiment_id=cond.id, compound_id=compound_b.id, amount=1.0, unit=AmountUnit.GRAM
    )
    db_session.add(additive_b)
    db_session.commit()
    db_session.refresh(additive_b)
    # Try to change additive_a's compound to compound_b (already in experiment)
    resp = client.patch(f"/api/additives/{additive_a.id}", json={"compound_id": compound_b.id})
    assert resp.status_code == 409


def test_patch_additive_wt_pct_fluid_computes_mass_in_grams(client, db_session):
    """PATCHing an additive to WT_PCT_FLUID should populate mass_in_grams via recalculation.

    wt% of fluid formula: mass_in_grams = (amount / 100) × water_volume_mL
    With amount=2.0 and water_volume_mL=500.0: expected mass_in_grams = 10.0
    """
    _, _, _, additive = _setup_experiment_with_additive(
        db_session, "ADDTEST_010", 6010, compound_name="FeO_wt_pct_fluid", amount=1.0, unit=AmountUnit.GRAM
    )
    resp = client.patch(f"/api/additives/{additive.id}", json={"unit": "wt% of fluid", "amount": 2.0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mass_in_grams"] == pytest.approx(10.0)


# ── DELETE /api/additives/{additive_id} ───────────────────────────────────────

def test_delete_additive_by_pk(client, db_session):
    _, _, _, additive = _setup_experiment_with_additive(db_session, "ADDTEST_008", 6008)
    additive_id = additive.id
    resp = client.delete(f"/api/additives/{additive_id}")
    assert resp.status_code == 204
    # Verify row is gone
    gone = db_session.get(ChemicalAdditive, additive_id)
    assert gone is None


def test_delete_additive_not_found_returns_404(client):
    resp = client.delete("/api/additives/99999")
    assert resp.status_code == 404


def test_delete_additive_writes_modifications_log(client, db_session):
    exp, cond, compound, additive = _setup_experiment_with_additive(db_session, "ADDTEST_009", 6009)
    additive_id = additive.id
    client.delete(f"/api/additives/{additive_id}")
    log_entry = db_session.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_fk == exp.id,
            ModificationsLog.modified_table == "chemical_additives",
            ModificationsLog.modification_type == "delete",
        )
    ).scalar_one_or_none()
    assert log_entry is not None
    assert log_entry.old_values["compound_id"] == compound.id
    assert log_entry.new_values is None


# --- Issue #96 addition_method length guard ---

def test_patch_additive_method_over_max_length_returns_422(client, db_session):
    from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
    _, _, _, additive = _setup_experiment_with_additive(db_session, "ADDTEST_I96_001", 96001)
    resp = client.patch(
        f"/api/additives/{additive.id}",
        json={"addition_method": "x" * (ADDITION_METHOD_MAX_LENGTH + 1)},
    )
    assert resp.status_code == 422


def test_patch_additive_method_at_max_length_succeeds(client, db_session):
    from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH
    _, _, _, additive = _setup_experiment_with_additive(db_session, "ADDTEST_I96_002", 96002)
    method_text = "x" * ADDITION_METHOD_MAX_LENGTH
    resp = client.patch(
        f"/api/additives/{additive.id}",
        json={"addition_method": method_text},
    )
    assert resp.status_code == 200
    assert resp.json()["addition_method"] == method_text


# --- Issue #109: GET/PUT/DELETE /api/experiments/{id}/additives must resolve
# conditions via experiment_fk, never the denormalized (and possibly stale)
# ExperimentalConditions.experiment_id string. ---

def _setup_experiment_with_stale_conditions(
    db, exp_id, stale_string, number,
    compound_name=None, amount=5.0,
    unit=AmountUnit.GRAM, with_additive=True,
):
    """Same shape as _setup_experiment_with_additive, but the conditions row's
    denormalized experiment_id string does NOT match the experiment's real ID
    -- simulating the debris a rename leaves when the string isn't synced
    (issue #109). Resolution must go through experiment_fk regardless.
    """
    exp = Experiment(experiment_id=exp_id, experiment_number=number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.flush()
    cond = ExperimentalConditions(
        experiment_id=stale_string,
        experiment_fk=exp.id,
        rock_mass_g=100.0,
        water_volume_mL=500.0,
    )
    db.add(cond)
    db.flush()
    additive = None
    compound = None
    if with_additive:
        compound = Compound(name=compound_name or f"{exp_id}_Compound", molecular_weight_g_mol=159.69)
        db.add(compound)
        db.flush()
        additive = ChemicalAdditive(
            experiment_id=cond.id,
            compound_id=compound.id,
            amount=amount,
            unit=unit,
        )
        db.add(additive)
    db.commit()
    if additive is not None:
        db.refresh(additive)
    if compound is not None:
        db.refresh(compound)
    db.refresh(exp)
    db.refresh(cond)
    return exp, cond, compound, additive


def test_get_additives_resolves_via_fk_despite_stale_string(client, db_session):
    """The 175-row case: the string names an experiment that has no
    conditions row, so a string-keyed lookup returned [] for an experiment
    that actually has additives."""
    exp, cond, compound, additive = _setup_experiment_with_stale_conditions(
        db_session, "ADDSTALE_001", "ADDSTALE_001_OLDNAME", 96101,
    )
    resp = client.get(f"/api/experiments/{exp.experiment_id}/additives")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["compound_id"] == compound.id


def test_get_additives_no_500_on_duplicate_stale_string(client, db_session):
    """The 6-row case: two different experiments' conditions rows share the
    same stale string. A string-keyed scalar_one_or_none() 500s on this
    (MultipleResultsFound); resolving via experiment_fk must not."""
    exp_a, cond_a, compound_a, _ = _setup_experiment_with_stale_conditions(
        db_session, "ADDSTALE_002", "ADDSTALE_SHARED", 96102,
    )
    exp_b, cond_b, compound_b, _ = _setup_experiment_with_stale_conditions(
        db_session, "ADDSTALE_003", "ADDSTALE_SHARED", 96103,
    )
    resp_a = client.get(f"/api/experiments/{exp_a.experiment_id}/additives")
    assert resp_a.status_code == 200
    assert resp_a.json()[0]["compound_id"] == compound_a.id

    resp_b = client.get(f"/api/experiments/{exp_b.experiment_id}/additives")
    assert resp_b.status_code == 200
    assert resp_b.json()[0]["compound_id"] == compound_b.id


def test_put_additive_resolves_via_fk_despite_stale_string(client, db_session):
    exp, cond, _, _ = _setup_experiment_with_stale_conditions(
        db_session, "ADDSTALE_004", "ADDSTALE_004_OLDNAME", 96104, with_additive=False,
    )
    compound = Compound(name="ADDSTALE_004_Compound", molecular_weight_g_mol=100.0)
    db_session.add(compound)
    db_session.commit()

    resp = client.put(
        f"/api/experiments/{exp.experiment_id}/additives/{compound.id}",
        json={"amount": 3.0, "unit": "g"},
    )
    assert resp.status_code == 200
    assert resp.json()["compound_id"] == compound.id

    row = db_session.execute(
        select(ChemicalAdditive).where(ChemicalAdditive.experiment_id == cond.id)
    ).scalar_one()
    assert row.compound_id == compound.id


def test_put_additive_does_not_write_to_wrong_experiment(client, db_session):
    """The worst pre-fix case (the 12-row group): experiment A's stale string
    names experiment B's real ID. A PUT for A must write onto A's own
    conditions row (via experiment_fk), never B's."""
    victim = Experiment(experiment_id="ADDSTALE_006", experiment_number=96106, status=ExperimentStatus.ONGOING)
    db_session.add(victim)
    db_session.flush()
    victim_cond = ExperimentalConditions(
        experiment_id="ADDSTALE_006", experiment_fk=victim.id, rock_mass_g=50.0,
    )
    db_session.add(victim_cond)
    db_session.commit()

    exp, cond, _, _ = _setup_experiment_with_stale_conditions(
        db_session, "ADDSTALE_005", "ADDSTALE_006", 96105, with_additive=False,
    )
    compound = Compound(name="ADDSTALE_005_Compound", molecular_weight_g_mol=80.0)
    db_session.add(compound)
    db_session.commit()

    resp = client.put(
        f"/api/experiments/{exp.experiment_id}/additives/{compound.id}",
        json={"amount": 2.0, "unit": "g"},
    )
    assert resp.status_code == 200

    victim_additives = db_session.execute(
        select(ChemicalAdditive).where(ChemicalAdditive.experiment_id == victim_cond.id)
    ).scalars().all()
    assert victim_additives == []

    own_additives = db_session.execute(
        select(ChemicalAdditive).where(ChemicalAdditive.experiment_id == cond.id)
    ).scalars().all()
    assert len(own_additives) == 1
    assert own_additives[0].compound_id == compound.id


def test_delete_additive_resolves_via_fk_despite_stale_string(client, db_session):
    exp, cond, compound, additive = _setup_experiment_with_stale_conditions(
        db_session, "ADDSTALE_007", "ADDSTALE_007_OLDNAME", 96107,
    )
    resp = client.delete(f"/api/experiments/{exp.experiment_id}/additives/{compound.id}")
    assert resp.status_code == 204
    gone = db_session.get(ChemicalAdditive, additive.id)
    assert gone is None
