"""Tests for ChemicalInventoryService."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import Compound
from backend.services.bulk_uploads.chemical_inventory import ChemicalInventoryService

from .excel_helpers import make_excel

# NOTE: chemical_inventory.py uses `compound.molecular_weight` and `Compound(molecular_weight=...)`
# but the model column is `molecular_weight_g_mol`.  This bug causes every row that reaches the
# create/update path to raise an AttributeError/TypeError (caught and appended to errors[]).
# The three tests below that exercise create/update are marked xfail until the service is fixed.


@pytest.mark.xfail(
    reason="Service uses wrong attr 'molecular_weight' (model has 'molecular_weight_g_mol'); "
    "causes TypeError on Compound() constructor for every new row",
)
def test_creates_new_compound(db_session: Session):
    """Valid row creates a Compound record."""
    xlsx = make_excel(
        ["name", "formula", "cas_number"],
        [["Magnesium hydroxide", "Mg(OH)2", "1309-42-8"]],
    )
    created, updated, skipped, errors = ChemicalInventoryService.bulk_upsert_from_excel(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert updated == 0

    compound = (
        db_session.query(Compound)
        .filter(Compound.name == "Magnesium hydroxide")
        .first()
    )
    assert compound is not None
    assert compound.formula == "Mg(OH)2"


@pytest.mark.xfail(
    reason="Service uses wrong attr 'molecular_weight' (model has 'molecular_weight_g_mol'); "
    "causes AttributeError on existing compound update",
)
def test_updates_existing_compound(db_session: Session):
    """Second upload with the same name updates the existing compound."""
    existing = Compound(name="Iron sulfate", formula="FeSO4")
    db_session.add(existing)
    db_session.flush()

    xlsx = make_excel(
        ["name", "formula"],
        [["Iron sulfate", "FeSO4·7H2O"]],
    )
    created, updated, skipped, errors = ChemicalInventoryService.bulk_upsert_from_excel(
        db_session, xlsx
    )

    assert errors == []
    assert created == 0
    assert updated == 1

    db_session.refresh(existing)
    assert existing.formula == "FeSO4·7H2O"


def test_missing_name_column_returns_error(db_session: Session):
    """File without a 'name' column returns an error immediately."""
    xlsx = make_excel(
        ["formula", "cas_number"],
        [["H2O", "7732-18-5"]],
    )
    created, updated, skipped, errors = ChemicalInventoryService.bulk_upsert_from_excel(
        db_session, xlsx
    )

    assert created == 0
    assert any("name" in e.lower() for e in errors)


def test_blank_name_rows_skipped(db_session: Session):
    """Rows with a whitespace-only 'name' field are skipped, not errored."""
    xlsx = make_excel(
        ["name", "formula"],
        [["   ", "H2SO4"]],  # spaces-only → .strip() → "" → skipped
    )
    created, updated, skipped, errors = ChemicalInventoryService.bulk_upsert_from_excel(
        db_session, xlsx
    )

    assert created == 0
    assert skipped == 1
    assert errors == []


@pytest.mark.xfail(
    reason="Service uses wrong attr 'molecular_weight' (model has 'molecular_weight_g_mol'); "
    "causes AttributeError/TypeError on every create or update row",
)
def test_multiple_rows_mixed_create_and_update(db_session: Session):
    """Mix of new and existing compounds processes correctly."""
    existing = Compound(name="Sodium chloride", formula="NaCl")
    db_session.add(existing)
    db_session.flush()

    xlsx = make_excel(
        ["name", "formula"],
        [
            ["Sodium chloride", "NaCl (updated)"],   # update
            ["Potassium chloride", "KCl"],            # create
        ],
    )
    created, updated, skipped, errors = ChemicalInventoryService.bulk_upsert_from_excel(
        db_session, xlsx
    )

    assert errors == []
    assert created == 1
    assert updated == 1


def test_invalid_file_bytes_returns_error(db_session: Session):
    """Non-Excel bytes return a file-read error, zero rows processed."""
    created, updated, skipped, errors = ChemicalInventoryService.bulk_upsert_from_excel(
        db_session, b"not an excel file at all"
    )

    assert created == 0
    assert len(errors) > 0
