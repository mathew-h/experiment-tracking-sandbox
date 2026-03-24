from database.models.samples import SampleInfo
from database.models.analysis import ExternalAnalysis, PXRFReading
from database.models.experiments import Experiment, ModificationsLog
from database.models.enums import ExperimentStatus


def _make_sample(db, sample_id="ROCK_T01"):
    s = SampleInfo(sample_id=sample_id, rock_classification="Peridotite")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _make_experiment(db, sample_id="ROCK_T01", experiment_id="HPHT_001"):
    from database.models.experiments import Experiment
    from database.models.enums import ExperimentStatus
    e = Experiment(
        experiment_id=experiment_id,
        experiment_number=9001,
        sample_id=sample_id,
        status=ExperimentStatus.ONGOING,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def test_list_samples_empty(client):
    resp = client.get("/api/samples")
    assert resp.status_code == 200


def test_get_sample_not_found(client):
    resp = client.get("/api/samples/NOPE")
    assert resp.status_code == 404


def test_get_sample_found(client, db_session):
    _make_sample(db_session, "ROCK_TEST_01")
    resp = client.get("/api/samples/ROCK_TEST_01")
    assert resp.status_code == 200
    assert resp.json()["rock_classification"] == "Peridotite"


def test_create_sample(client):
    payload = {"sample_id": "ROCK_NEW_01", "rock_classification": "Dunite", "country": "USA"}
    resp = client.post("/api/samples", json=payload)
    assert resp.status_code == 201
    assert resp.json()["sample_id"] == "ROCK_NEW_01"


def test_patch_sample(client, db_session):
    _make_sample(db_session, "ROCK_PATCH_01")
    resp = client.patch("/api/samples/ROCK_PATCH_01", json={"country": "Canada"})
    assert resp.status_code == 200
    assert resp.json()["country"] == "Canada"


# --- List endpoint (SampleListItem) ---

def test_list_samples_returns_list_items(client, db_session):
    _make_sample(db_session, "LIST_S01")
    resp = client.get("/api/samples")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    item = next(i for i in data["items"] if i["sample_id"] == "LIST_S01")
    assert "experiment_count" in item
    assert "has_pxrf" in item
    assert "has_xrd" in item
    assert "has_elemental" in item


def test_list_samples_filter_characterized(client, db_session):
    s = _make_sample(db_session, "LIST_S02")
    s.characterized = True
    db_session.commit()
    resp = client.get("/api/samples", params={"characterized": "true"})
    assert resp.status_code == 200
    ids = [i["sample_id"] for i in resp.json()["items"]]
    assert "LIST_S02" in ids


def test_list_samples_search(client, db_session):
    _make_sample(db_session, "SEARCH_UNIQUE_XYZ")
    resp = client.get("/api/samples", params={"search": "SEARCH_UNIQUE"})
    assert resp.status_code == 200
    ids = [i["sample_id"] for i in resp.json()["items"]]
    assert "SEARCH_UNIQUE_XYZ" in ids


# --- Geo endpoint ---

def test_get_geo_returns_only_samples_with_coords(client, db_session):
    s1 = _make_sample(db_session, "GEO_S01")
    s1.latitude = 40.0
    s1.longitude = -74.0
    _make_sample(db_session, "GEO_S02")  # no coords
    db_session.commit()
    resp = client.get("/api/samples/geo")
    assert resp.status_code == 200
    ids = [i["sample_id"] for i in resp.json()]
    assert "GEO_S01" in ids
    assert "GEO_S02" not in ids


# --- Delete endpoint ---

def test_delete_sample_no_experiments(client, db_session):
    _make_sample(db_session, "DEL_S01")
    resp = client.delete("/api/samples/DEL_S01")
    assert resp.status_code == 204
    assert client.get("/api/samples/DEL_S01").status_code == 404


def test_delete_sample_with_experiments_returns_409(client, db_session):
    _make_sample(db_session, "DEL_S02")
    _make_experiment(db_session, sample_id="DEL_S02", experiment_id="DEL_EXP_001")
    resp = client.delete("/api/samples/DEL_S02")
    assert resp.status_code == 409


# --- Detail endpoint (SampleDetail) ---

def test_get_sample_detail_structure(client, db_session):
    _make_sample(db_session, "DETAIL_S01")
    resp = client.get("/api/samples/DETAIL_S01")
    assert resp.status_code == 200
    data = resp.json()
    assert "photos" in data
    assert "analyses" in data
    assert "experiments" in data
