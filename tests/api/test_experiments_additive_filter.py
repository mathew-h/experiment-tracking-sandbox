from __future__ import annotations

from database.models.chemicals import ChemicalAdditive, Compound
from database.models.conditions import ExperimentalConditions
from database.models.enums import AmountUnit, ExperimentStatus
from database.models.experiments import Experiment


def _seed(db):
    """ADDF_001 nickel chloride, ADDF_002 magnetite, ADDF_003 no additives."""
    rows = [
        ("ADDF_001", 7101, "ADDF Nickel chloride"),
        ("ADDF_002", 7102, "ADDF Magnetite"),
        ("ADDF_003", 7103, None),
    ]
    for exp_id, number, compound_name in rows:
        exp = Experiment(
            experiment_id=exp_id,
            experiment_number=number,
            status=ExperimentStatus.ONGOING,
        )
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
        if compound_name:
            compound = Compound(name=compound_name, molecular_weight_g_mol=100.0)
            db.add(compound)
            db.flush()
            db.add(
                ChemicalAdditive(
                    experiment_id=cond.id,
                    compound_id=compound.id,
                    amount=1.0,
                    unit=AmountUnit.GRAM,
                )
            )
    db.flush()


def _ids(resp):
    assert resp.status_code == 200
    return [i["experiment_id"] for i in resp.json()["items"]]


def test_additive_filter_partial_case_insensitive(client, db_session):
    _seed(db_session)
    resp = client.get("/api/experiments?additive=nickel&search=ADDF_")
    assert _ids(resp) == ["ADDF_001"]
    assert resp.json()["total"] == 1


def test_additive_filter_combines_with_other_filters(client, db_session):
    _seed(db_session)
    resp = client.get("/api/experiments?additive=addf&search=ADDF_002")
    assert _ids(resp) == ["ADDF_002"]


def test_additive_filter_grouped_mode(client, db_session):
    _seed(db_session)
    resp = client.get(
        "/api/experiments?additive=magnetite&search=ADDF_&group_replicates=true"
    )
    assert _ids(resp) == ["ADDF_002"]


def test_no_additive_param_is_unchanged(client, db_session):
    _seed(db_session)
    resp = client.get("/api/experiments?search=ADDF_")
    assert len(_ids(resp)) == 3
