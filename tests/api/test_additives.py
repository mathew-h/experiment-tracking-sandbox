from __future__ import annotations
from database.models.experiments import Experiment, ModificationsLog
from database.models.conditions import ExperimentalConditions
from database.models.chemicals import Compound, ChemicalAdditive
from database.models.enums import ExperimentStatus, AmountUnit
from sqlalchemy import select


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
