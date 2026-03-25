from __future__ import annotations
import pytest
from database.models.chemicals import Compound


def _make_compound(db, name="TestCompound", cas_number=None):
    c = Compound(name=name, formula="TestF", molecular_weight_g_mol=100.0, cas_number=cas_number)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# --- list / search ---

def test_list_compounds_empty(client):
    resp = client.get("/api/chemicals/compounds")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_compounds_search(client, db_session):
    _make_compound(db_session, "Magnesium Hydroxide")
    _make_compound(db_session, "Iron Chloride")

    resp = client.get("/api/chemicals/compounds?search=magnes")
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "Magnesium Hydroxide" in names
    assert "Iron Chloride" not in names


def test_list_compounds_search_case_insensitive(client, db_session):
    _make_compound(db_session, "Sodium Chloride")
    resp = client.get("/api/chemicals/compounds?search=SODIUM")
    assert resp.status_code == 200
    assert any(c["name"] == "Sodium Chloride" for c in resp.json())


# --- create ---

def test_create_compound(client):
    resp = client.post("/api/chemicals/compounds", json={
        "name": "Magnesium Hydroxide", "formula": "Mg(OH)2", "molecular_weight_g_mol": 58.32
    })
    assert resp.status_code == 201
    assert resp.json()["name"] == "Magnesium Hydroxide"


def test_create_compound_name_too_short(client):
    resp = client.post("/api/chemicals/compounds", json={"name": "X"})
    assert resp.status_code == 422


def test_create_compound_duplicate_name_case_insensitive(client, db_session):
    _make_compound(db_session, "Iron Oxide")
    resp = client.post("/api/chemicals/compounds", json={"name": "iron oxide"})
    assert resp.status_code == 409


def test_create_compound_duplicate_cas(client, db_session):
    _make_compound(db_session, "CompoundA", cas_number="1234-56-7")
    resp = client.post("/api/chemicals/compounds", json={
        "name": "CompoundB", "cas_number": "1234-56-7"
    })
    assert resp.status_code == 409


def test_create_compound_invalid_cas_format(client):
    resp = client.post("/api/chemicals/compounds", json={
        "name": "BadCAS", "cas_number": "abc-def"
    })
    assert resp.status_code == 422


# --- get ---

def test_get_compound_not_found(client):
    resp = client.get("/api/chemicals/compounds/99999")
    assert resp.status_code == 404


def test_get_compound(client, db_session):
    c = _make_compound(db_session, "IronChloride")
    resp = client.get(f"/api/chemicals/compounds/{c.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "IronChloride"


# --- PATCH ---

def test_patch_compound(client, db_session):
    c = _make_compound(db_session, "OldName")
    resp = client.patch(f"/api/chemicals/compounds/{c.id}", json={"name": "NewNameX"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "NewNameX"


def test_patch_compound_not_found(client):
    resp = client.patch("/api/chemicals/compounds/99999", json={"name": "X" * 5})
    assert resp.status_code == 404


def test_patch_compound_duplicate_name(client, db_session):
    _make_compound(db_session, "AlreadyExists")
    c2 = _make_compound(db_session, "ToBeRenamed")
    resp = client.patch(f"/api/chemicals/compounds/{c2.id}", json={"name": "alreadyexists"})
    assert resp.status_code == 409


def test_patch_compound_duplicate_cas(client, db_session):
    _make_compound(db_session, "CompA", cas_number="9999-00-1")
    c2 = _make_compound(db_session, "CompB")
    resp = client.patch(f"/api/chemicals/compounds/{c2.id}", json={"cas_number": "9999-00-1"})
    assert resp.status_code == 409
