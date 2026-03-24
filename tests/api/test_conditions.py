import datetime

import pytest
from sqlalchemy import select
from database.models.analysis import ExternalAnalysis
from database.models.characterization import ElementalAnalysis, Analyte
from database.models.enums import ExperimentStatus
from database.models.experiments import Experiment
from database.models.samples import SampleInfo


def _make_experiment(db, eid="COND_EXP_001", num=7001):
    exp = Experiment(experiment_id=eid, experiment_number=num, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def test_create_conditions_triggers_calculation(client, db_session):
    exp = _make_experiment(db_session)
    payload = {
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "rock_mass_g": 10.0,
        "water_volume_mL": 50.0,
    }
    resp = client.post("/api/conditions", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    # water_to_rock_ratio is a persisted Float column (conditions.py line 33)
    # The calc engine writes it directly; it is NOT a @hybrid_property.
    assert data["water_to_rock_ratio"] == 5.0  # 50/10


def test_get_conditions(client, db_session):
    exp = _make_experiment(db_session, "COND_EXP_002", 7002)
    payload = {"experiment_fk": exp.id, "experiment_id": exp.experiment_id, "temperature_c": 180.0}
    created = client.post("/api/conditions", json=payload).json()
    resp = client.get(f"/api/conditions/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["temperature_c"] == 180.0


def _seed_sample_with_feo(db, sample_id="IRON_SAMPLE_001", feo_wt_pct=10.0):
    """Insert SampleInfo + ExternalAnalysis + ElementalAnalysis + Analyte for FeO.

    Uses analysis_type='Bulk Elemental Composition' to match the wide-format
    ElementalCompositionService uploader (production path for pre-exp FeO).
    """
    sample = SampleInfo(sample_id=sample_id)
    db.add(sample)
    db.flush()

    analyte = db.execute(
        select(Analyte).where(Analyte.analyte_symbol == "FeO")
    ).scalar_one_or_none()
    if analyte is None:
        analyte = Analyte(analyte_symbol="FeO", unit="%")
        db.add(analyte)
        db.flush()

    ext = ExternalAnalysis(
        sample_id=sample_id,
        analysis_type="Bulk Elemental Composition",
        analysis_date=datetime.datetime(2025, 1, 1),
    )
    db.add(ext)
    db.flush()

    ea = ElementalAnalysis(
        external_analysis_id=ext.id,
        sample_id=sample_id,
        analyte_id=analyte.id,
        analyte_composition=feo_wt_pct,
    )
    db.add(ea)
    db.commit()
    return sample


def test_total_ferrous_iron_g_populated_on_create(client, db_session):
    """POST /conditions: field is computed when sample has FeO analysis."""
    _seed_sample_with_feo(db_session, feo_wt_pct=10.0)
    exp = _make_experiment(db_session, eid="IRON_EXP_001", num=8001)
    # Link the experiment to the sample
    exp.sample_id = "IRON_SAMPLE_001"
    db_session.commit()

    payload = {
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "rock_mass_g": 5.0,
    }
    resp = client.post("/api/conditions", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_ferrous_iron_g"] == pytest.approx(0.38866, rel=1e-3)


def test_total_ferrous_iron_g_none_when_no_analysis(client, db_session):
    """POST /conditions: field is None when sample has no FeO characterization."""
    exp = _make_experiment(db_session, eid="NO_FEO_EXP_001", num=8002)
    payload = {
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "rock_mass_g": 5.0,
    }
    resp = client.post("/api/conditions", json=payload)
    assert resp.status_code == 201
    assert resp.json()["total_ferrous_iron_g"] is None


def test_total_ferrous_iron_g_recalculated_on_patch(client, db_session):
    """PATCH /conditions: field updates when rock_mass_g changes."""
    _seed_sample_with_feo(db_session, sample_id="IRON_SAMPLE_003", feo_wt_pct=10.0)
    exp = _make_experiment(db_session, eid="IRON_EXP_003", num=8003)
    exp.sample_id = "IRON_SAMPLE_003"
    db_session.commit()

    created = client.post("/api/conditions", json={
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "rock_mass_g": 5.0,
    }).json()
    assert created["total_ferrous_iron_g"] == pytest.approx(0.38866, rel=1e-3)

    patched = client.patch(f"/api/conditions/{created['id']}", json={"rock_mass_g": 10.0})
    assert patched.status_code == 200
    # Double the rock_mass → double the iron
    assert patched.json()["total_ferrous_iron_g"] == pytest.approx(0.77731, rel=1e-3)
