from database.models.samples import SampleInfo


def _make_sample(db, sample_id="ROCK_T01"):
    s = SampleInfo(sample_id=sample_id, rock_classification="Peridotite")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


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
