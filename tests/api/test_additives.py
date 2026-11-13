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


# ── Issue #190 (D-07): one additive service, audit rows signed with the email ──

_EMAIL = "test@addisenergy.com"  # conftest _FAKE_USER.email; its uid is "test-uid"


def _additive_logs(db, exp, modification_type):
    return db.execute(
        select(ModificationsLog).where(
            ModificationsLog.experiment_fk == exp.id,
            ModificationsLog.modified_table == "chemical_additives",
            ModificationsLog.modification_type == modification_type,
        ).order_by(ModificationsLog.id)
    ).scalars().all()


def test_put_additive_create_recalculates_and_signs_with_the_email(client, db_session):
    exp, _cond, _compound, _existing = _setup_experiment_with_additive(db_session, "ADDSVC_001", 6101)
    other = Compound(name="ADDSVC Nickel Chloride", molecular_weight_g_mol=129.6)
    db_session.add(other)
    db_session.commit()

    resp = client.put(f"/api/experiments/ADDSVC_001/additives/{other.id}", json={"amount": 5.0, "unit": "mM"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 5 mM in 500 mL = 2.5 mmol; x 129.6 g/mol = 0.324 g. Stored, not NULL: the
    # explicit post-flush recalculate is what fills these for concentration units.
    assert body["moles_added"] == pytest.approx(0.0025)
    assert body["mass_in_grams"] == pytest.approx(0.324)

    (entry,) = _additive_logs(db_session, exp, "create")
    assert entry.modified_by == _EMAIL
    assert entry.experiment_id == "ADDSVC_001"
    assert entry.old_values is None
    assert entry.new_values == {"amount": 5.0, "unit": "mM"}


def test_put_additive_update_logs_amount_and_unit_before_and_after(client, db_session):
    exp, _cond, compound, additive = _setup_experiment_with_additive(db_session, "ADDSVC_002", 6102,
                                                                     compound_name="ADDSVC Iron Oxide")
    resp = client.put(f"/api/experiments/ADDSVC_002/additives/{compound.id}", json={"amount": 9.0, "unit": "g"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == additive.id  # updated in place, not duplicated
    assert resp.json()["mass_in_grams"] == pytest.approx(9.0)

    (entry,) = _additive_logs(db_session, exp, "update")
    assert entry.modified_by == _EMAIL
    assert entry.old_values == {"amount": 5.0, "unit": "g"}
    assert entry.new_values == {"amount": 9.0, "unit": "g"}


def test_delete_experiment_additive_logs_the_snapshot_with_the_email(client, db_session):
    exp, _cond, compound, additive = _setup_experiment_with_additive(db_session, "ADDSVC_003", 6103,
                                                                     compound_name="ADDSVC Magnetite")
    additive_id = additive.id
    assert client.delete(f"/api/experiments/ADDSVC_003/additives/{compound.id}").status_code == 204
    db_session.expire_all()
    assert db_session.get(ChemicalAdditive, additive_id) is None

    (entry,) = _additive_logs(db_session, exp, "delete")
    assert entry.modified_by == _EMAIL
    assert entry.old_values == {
        "compound_id": compound.id, "compound_name": "ADDSVC Magnetite", "amount": 5.0, "unit": "g",
    }
    assert entry.new_values is None


def test_both_delete_routes_write_the_same_audit_payload(client, db_session):
    exp_a, _c, compound_a, _a = _setup_experiment_with_additive(db_session, "ADDSVC_004", 6104,
                                                                 compound_name="ADDSVC Hematite A")
    exp_b, _c, _compound_b, additive_b = _setup_experiment_with_additive(db_session, "ADDSVC_005", 6105,
                                                                         compound_name="ADDSVC Hematite B")
    assert client.delete(f"/api/experiments/ADDSVC_004/additives/{compound_a.id}").status_code == 204
    assert client.delete(f"/api/additives/{additive_b.id}").status_code == 204

    (by_compound,) = _additive_logs(db_session, exp_a, "delete")
    (by_pk,) = _additive_logs(db_session, exp_b, "delete")
    assert by_compound.modified_by == by_pk.modified_by == _EMAIL
    assert set(by_compound.old_values) == set(by_pk.old_values) == {"compound_id", "compound_name", "amount", "unit"}


def test_patch_additive_logs_a_unit_change_as_plain_text(client, db_session):
    exp, _cond, _compound, additive = _setup_experiment_with_additive(db_session, "ADDSVC_006", 6106,
                                                                      compound_name="ADDSVC Siderite")
    assert client.patch(f"/api/additives/{additive.id}", json={"unit": "mg"}).status_code == 200
    (entry,) = _additive_logs(db_session, exp, "update")
    assert entry.modified_by == _EMAIL
    assert entry.old_values == {"unit": "g"}
    assert entry.new_values == {"unit": "mg"}


def test_experiment_patch_audit_rows_are_signed_with_the_email(client, db_session):
    """Decision H-05: update_experiment used to sign with the Firebase uid."""
    exp, *_ = _setup_experiment_with_additive(db_session, "ADDSVC_007", 6107, compound_name="ADDSVC Pyrite")
    assert client.patch("/api/experiments/ADDSVC_007", json={"is_outlier": True}).status_code == 200
    rows = db_session.execute(
        select(ModificationsLog).where(ModificationsLog.experiment_fk == exp.id)
    ).scalars().all()
    assert rows and {r.modified_by for r in rows} == {_EMAIL}
