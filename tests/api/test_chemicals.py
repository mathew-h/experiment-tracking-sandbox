from database.models.chemicals import Compound


def _make_compound(db, name="TestCompound"):
    c = Compound(name=name, formula="TestF", molecular_weight_g_mol=100.0)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_list_compounds_empty(client):
    resp = client.get("/api/chemicals/compounds")
    assert resp.status_code == 200


def test_create_compound(client):
    resp = client.post("/api/chemicals/compounds", json={
        "name": "Magnesium Hydroxide", "formula": "Mg(OH)2", "molecular_weight_g_mol": 58.32
    })
    assert resp.status_code == 201
    assert resp.json()["name"] == "Magnesium Hydroxide"


def test_get_compound_not_found(client):
    resp = client.get("/api/chemicals/compounds/99999")
    assert resp.status_code == 404


def test_get_compound(client, db_session):
    c = _make_compound(db_session, "IronChloride")
    resp = client.get(f"/api/chemicals/compounds/{c.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "IronChloride"
