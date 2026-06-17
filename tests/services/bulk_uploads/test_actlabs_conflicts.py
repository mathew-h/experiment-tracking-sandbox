"""Tests for ActlabsRockTitrationService preflight and resolution logic."""
from __future__ import annotations

import io
import pandas as pd
import pytest

from database import SampleInfo
from backend.services.bulk_uploads.actlabs_titration_data import ActlabsRockTitrationService


def _make_csv(sample_ids: list[str]) -> bytes:
    """Build a minimal ActLabs-like CSV with the given sample IDs."""
    rows = [
        ["Report Number", "", ""],
        ["Report Date", "", ""],
        ["Sample ID", "FeO", "SiO2"],
        ["", "%", "%"],
        ["Detection Limit", "0.01", "0.01"],
        ["Analysis Method: titration", "", ""],
        *[[sid, 10.0, 40.0] for sid in sample_ids],
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, header=False, index=False)
    buf.seek(0)
    return buf.getvalue()


# ── preflight_check ───────────────────────────────────────────────────────────

def test_preflight_no_conflicts(db_session):
    """Exact match → no conflicts returned."""
    db_session.add(SampleInfo(sample_id="Granite"))
    db_session.flush()
    conflicts, auto_log = ActlabsRockTitrationService.preflight_check(
        db_session, _make_csv(["Granite"])
    )
    assert conflicts == []


def test_preflight_exact_case_auto_resolved(db_session):
    """Case-only difference is auto-resolved; not returned as conflict."""
    db_session.add(SampleInfo(sample_id="Tamarack"))
    db_session.flush()
    conflicts, auto_log = ActlabsRockTitrationService.preflight_check(
        db_session, _make_csv(["TAMARACK"])
    )
    assert conflicts == []
    assert any("TAMARACK" in entry for entry in auto_log)


def test_preflight_near_match_returned_as_conflict(db_session):
    """Near-match (typo) above default threshold produces a conflict entry."""
    db_session.add(SampleInfo(sample_id="Tamarack"))
    db_session.flush()
    conflicts, _ = ActlabsRockTitrationService.preflight_check(
        db_session, _make_csv(["Tamarrack"]), threshold=0.85
    )
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["incoming_id"] == "Tamarrack"
    assert len(c["candidate_matches"]) >= 1
    assert c["candidate_matches"][0]["sample_id"] == "Tamarack"


def test_preflight_no_existing_samples_no_conflicts(db_session):
    """No existing samples → no conflicts (sample not found, but not a conflict)."""
    conflicts, auto_log = ActlabsRockTitrationService.preflight_check(
        db_session, _make_csv(["NewSample"])
    )
    assert conflicts == []


# ── import_excel with resolutions ────────────────────────────────────────────

def test_import_link_resolution(db_session):
    """Resolution 'link:<id>' maps incoming ID to an existing sample."""
    db_session.add(SampleInfo(sample_id="Tamarack"))
    db_session.flush()

    resolutions = {"Tamarrack": "link:Tamarack"}
    created, updated, skipped, errors = ActlabsRockTitrationService.import_excel(
        db_session, _make_csv(["Tamarrack"]), resolutions=resolutions
    )
    assert errors == []
    assert created + updated > 0


def test_import_create_resolution(db_session):
    """Resolution 'create' creates a new SampleInfo record and imports results."""
    resolutions = {"BrandNew": "create"}
    created, updated, skipped, errors = ActlabsRockTitrationService.import_excel(
        db_session, _make_csv(["BrandNew"]), resolutions=resolutions
    )
    assert errors == []
    new_sample = db_session.query(SampleInfo).filter(SampleInfo.sample_id == "BrandNew").first()
    assert new_sample is not None


def test_import_no_resolution_still_errors(db_session):
    """No resolution for an unmatched ID → error row (existing behavior preserved)."""
    resolutions = {}
    _, _, _, errors = ActlabsRockTitrationService.import_excel(
        db_session, _make_csv(["NoMatch999"]), resolutions=resolutions
    )
    assert any("NoMatch999" in e for e in errors)
