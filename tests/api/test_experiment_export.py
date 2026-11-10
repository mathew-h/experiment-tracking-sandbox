"""Export all (issue #141): GET /api/experiments/{experiment_id}/export.

The workbook is read back with openpyxl and compared to the reporting views
(the same rows Power BI reads). Views are DDL created inside the test
transaction, as in tests/api/test_core_flood_view.py.
"""
import io
from datetime import date, datetime, timezone

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from backend.services import experiment_export
from backend.services.workdays import LAB_TZ
from database.models import Experiment, ExperimentalResults, ScalarResults
from database.models.chemicals import ChemicalAdditive, Compound
from database.models.conditions import ExperimentalConditions
from database.models.enums import AmountUnit, ExperimentStatus, NoteType
from database.models.experiments import ExperimentNotes
from database.models.results import ICPResults
from database.models.analysis import ExternalAnalysis
from database.models.samples import SampleInfo
from database.models.xrd import XRDPhase

# 23:30 lab time on 2026-11-06 is already 2026-11-07 in UTC.
_FROZEN_NOW = datetime(2026, 11, 6, 23, 30, tzinfo=LAB_TZ)


@pytest.fixture()
def reporting_views(db_session):
    from database.event_listeners import _VIEWS
    for view_name, _ in _VIEWS:
        db_session.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE"))
    for _, view_sql in _VIEWS:
        db_session.execute(text(view_sql))
    db_session.flush()
    yield


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    monkeypatch.setattr(experiment_export, "lab_now", lambda: _FROZEN_NOW)


_NUM = iter(range(98500, 99000))


def _experiment(db, exp_id, *, date_=None, status=ExperimentStatus.COMPLETED,
                experiment_type="Core Flood", description=None):
    exp = Experiment(experiment_id=exp_id, experiment_number=next(_NUM),
                     status=status, date=date_)
    db.add(exp)
    db.flush()
    db.add(ExperimentalConditions(
        experiment_fk=exp.id, experiment_id=exp.experiment_id,
        experiment_type=experiment_type, reactor_number=3, pore_volume_mL=20.0,
        rock_mass_g=50.0, temperature_c=90.0,
    ))
    if description:
        db.add(ExperimentNotes(experiment_fk=exp.id, experiment_id=exp.experiment_id,
                               note_text=description, note_type=NoteType.description))
    db.flush()
    return exp


def _sample(db, exp, cum_days, *, flow=0.1, measured=None, h2_ppm=None, icp=None,
            tube=None, ph=7.5):
    result = ExperimentalResults(
        experiment_fk=exp.id,
        cumulative_time_post_reaction_days=cum_days,
        time_post_reaction_days=cum_days,
        time_post_reaction_bucket_days=cum_days,
        is_primary_timepoint_result=True,
        flow_rate_mL_min=flow,
        sample_tube_number=tube,
    )
    db.add(result)
    db.flush()
    db.add(ScalarResults(result_id=result.id, sampling_volume_mL=5.0, final_ph=ph,
                         h2_grams_per_ton_yield=0.2, h2_concentration=h2_ppm,
                         h2_concentration_unit="ppm" if h2_ppm is not None else None,
                         measurement_date=measured))
    if icp:
        db.add(ICPResults(result_id=result.id, **icp))
    db.flush()
    return result


def _lab(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=LAB_TZ)


def _seed_run(db):
    """CFE_001 -> CFE_001-2, plus the side sample CFE_001-2_Bypass1."""
    root = _experiment(db, "CFE_001", date_=_lab(2026, 10, 1, 9),
                       description="Olivine core, Ni catalyst")
    seg2 = _experiment(db, "CFE_001-2", date_=_lab(2026, 10, 10, 9),
                       status=ExperimentStatus.ONGOING)
    bypass = _experiment(db, "CFE_001-2_Bypass1", date_=_lab(2026, 10, 10, 9))
    assert bypass.parent_experiment_fk == seg2.id

    r1 = _sample(db, root, 1.0, measured=_lab(2026, 10, 2), h2_ppm=1200.0,
                 icp={"fe": 3.5, "ni": 0.25}, tube=1)
    _sample(db, root, 4.0, measured=_lab(2026, 10, 5), tube=2)
    _sample(db, seg2, 10.0, measured=_lab(2026, 10, 11), h2_ppm=800.0,
            icp={"fe": 2.0, "mg": 11.0}, tube=3, flow=0.0)
    _sample(db, bypass, 10.0, measured=_lab(2026, 10, 11, 14, 30), ph=8.0)

    compound = Compound(name="CFE_NiCl2", formula="NiCl2", molecular_weight_g_mol=129.6)
    db.add(compound)
    db.flush()
    cond = db.execute(text("SELECT id FROM experimental_conditions"
                           " WHERE experiment_fk = :f"), {"f": root.id}).scalar_one()
    db.add(ChemicalAdditive(experiment_id=cond, compound_id=compound.id,
                            amount=1.5, unit=AmountUnit.GRAM, addition_order=1))
    db.add(ExperimentNotes(experiment_fk=root.id, experiment_id=root.experiment_id,
                           result_id=r1.id, note_type=NoteType.result_note,
                           note_text="cloudy", created_by="a@addisenergy.com"))
    db.add(ExperimentNotes(experiment_fk=seg2.id, experiment_id=seg2.experiment_id,
                           note_type=NoteType.modification,
                           event_date=date(2026, 10, 12),
                           note_text="swapped pump"))
    db.flush()
    return root, seg2, bypass


def _get(client, exp_id):
    resp = client.get(f"/api/experiments/{exp_id}/export")
    assert resp.status_code == 200, resp.text
    return resp, load_workbook(io.BytesIO(resp.content))


def _table(ws):
    rows = list(ws.iter_rows(values_only=True))
    headers = list(rows[0])
    return headers, [dict(zip(headers, r)) for r in rows[1:]]


def _view(db, sql, **params):
    return [dict(r) for r in db.execute(text(sql), params).mappings()]


def _naive_lab(dt):
    return dt.astimezone(LAB_TZ).replace(tzinfo=None) if dt is not None else None


# ---------------------------------------------------------------------------


def test_response_is_xlsx_with_lab_local_filename(client, db_session, reporting_views):
    _seed_run(db_session)
    resp, _wb = _get(client, "CFE_001")
    assert resp.headers["content-type"] == experiment_export.XLSX_MIME
    assert resp.headers["content-disposition"] == (
        'attachment; filename="CFE_001_export_2026-11-06.xlsx"')


def test_core_flood_run_has_all_tabs(client, db_session, reporting_views):
    _seed_run(db_session)
    _resp, wb = _get(client, "CFE_001")
    assert wb.sheetnames == ["Results", "Core Flood", "Conditions", "Additives",
                             "Notes", "Summary"]
    for ws in wb.worksheets:
        assert ws.freeze_panes == "A2"


def test_non_core_flood_has_no_core_flood_tab(client, db_session, reporting_views):
    exp = _experiment(db_session, "HPE_001", experiment_type="HPHT")
    _sample(db_session, exp, 3.0, measured=_lab(2026, 10, 4))
    _resp, wb = _get(client, "HPE_001")
    assert wb.sheetnames == ["Results", "Conditions", "Additives", "Notes", "Summary"]


def test_segment_id_exports_the_whole_lineage(client, db_session, reporting_views):
    _seed_run(db_session)
    _r1, by_root = _get(client, "CFE_001")
    r2, by_segment = _get(client, "CFE_001-2")
    _r3, by_variant = _get(client, "CFE_001-2_Bypass1")
    assert 'filename="CFE_001_export_' in r2.headers["content-disposition"]
    for other in (by_segment, by_variant):
        assert other.sheetnames == by_root.sheetnames
        for name in by_root.sheetnames:
            assert (list(other[name].iter_rows(values_only=True))
                    == list(by_root[name].iter_rows(values_only=True))), name


def test_results_rows_ordered_and_variant_flagged(client, db_session, reporting_views):
    _seed_run(db_session)
    _resp, wb = _get(client, "CFE_001")
    _h, rows = _table(wb["Results"])
    assert [(r["Experiment ID"], r["Cumulative day"]) for r in rows] == [
        ("CFE_001", 1.0), ("CFE_001", 4.0),
        ("CFE_001-2", 10.0), ("CFE_001-2_Bypass1", 10.0)]
    assert [r["is_variant"] for r in rows] == [False, False, False, True]


def test_results_values_match_views(client, db_session, reporting_views):
    root, seg2, bypass = _seed_run(db_session)
    fks = [root.id, seg2.id, bypass.id]
    _resp, wb = _get(client, "CFE_001")
    _h, rows = _table(wb["Results"])
    scalar = {r["result_id"]: r for r in _view(
        db_session, "SELECT * FROM v_results_scalar WHERE experiment_fk = ANY(:f)",
        f=fks)}
    h2 = {r["result_id"]: r for r in _view(
        db_session, "SELECT * FROM v_results_h2 WHERE experiment_fk = ANY(:f)", f=fks)}
    icp = {r["result_id"]: r for r in _view(
        db_session, "SELECT * FROM v_results_icp WHERE experiment_fk = ANY(:f)", f=fks)}
    tp = {r["result_id"]: r for r in _view(
        db_session,
        "SELECT * FROM v_dim_timepoints WHERE experiment_id LIKE 'CFE_001%'")}
    assert {r["Result ID"] for r in rows} == set(scalar)
    for row in rows:
        rid = row["Result ID"]
        s = scalar[rid]
        assert row["pH"] == pytest.approx(s["final_ph"])
        assert row["Sampling volume (mL)"] == pytest.approx(s["sampling_volume_mL"])
        assert row["Cumulative Fe2+ yield, H2-derived (%)"] == pytest.approx(
            s["cumulative_ferrous_iron_yield_h2_pct"])
        assert row["Sample date"] == _naive_lab(s["scalar_measurement_date"])
        assert row["Tube number"] == tp[rid]["sample_tube_number"]
        assert row["H2 (ppm)"] == (h2[rid]["h2_concentration"] if rid in h2 else None)
        assert row["H2 yield (g/t)"] == (
            pytest.approx(h2[rid]["h2_grams_per_ton_yield"]) if rid in h2 else None)
        for el in ("fe", "mg", "ni"):
            expected = icp[rid][f"{el}_ppm"] if rid in icp else None
            assert row[f"{el.capitalize()} (ppm)"] == expected, (rid, el)


def test_icp_columns_only_elements_with_readings_in_order(
        client, db_session, reporting_views):
    _seed_run(db_session)
    _resp, wb = _get(client, "CFE_001")
    headers, _rows = _table(wb["Results"])
    icp_headers = [h for h in headers if h.endswith("(ppm)") and not h.startswith("H2")]
    # ICP_ELEMENTS order is fe, si, mg, ca, ni, ...
    assert icp_headers == ["Fe (ppm)", "Mg (ppm)", "Ni (ppm)"]
    assert headers[-1] == "Modification note"


def test_dates_are_excel_dates_in_lab_time(client, db_session, reporting_views):
    _seed_run(db_session)
    _resp, wb = _get(client, "CFE_001")
    ws = wb["Results"]
    headers = [c.value for c in ws[1]]
    col = headers.index("Sample date") + 1
    cells = [ws.cell(row=i, column=col) for i in range(2, ws.max_row + 1)]
    assert all(isinstance(c.value, datetime) for c in cells)
    # Lab midnight, not 04:00 UTC; the bypass sample has a time of day, so the
    # column keeps hours and minutes.
    assert cells[0].value == datetime(2026, 10, 2, 0, 0)
    assert cells[-1].value == datetime(2026, 10, 11, 14, 30)
    assert cells[0].number_format == "yyyy-mm-dd hh:mm"

    notes = wb["Notes"]
    _h, rows = _table(notes)
    dated = [r for r in rows if r["Event date"] is not None]
    assert [r["Event date"] for r in dated] == [datetime(2026, 10, 12)]


def test_core_flood_values_match_view(client, db_session, reporting_views):
    root, seg2, bypass = _seed_run(db_session)
    _resp, wb = _get(client, "CFE_001")
    _h, rows = _table(wb["Core Flood"])
    view = {r["result_id"]: r for r in _view(
        db_session, "SELECT * FROM v_core_flood_samples WHERE run_base_id = 'CFE_001'")}
    assert {r["Result ID"] for r in rows} == set(view)
    for row in rows:
        v = view[row["Result ID"]]
        assert row["is_variant"] == v["is_variant"]
        assert row["Flow (mL/min)"] == v["flow_rate_mL_min"]
        assert row["Hold interval"] == v["is_hold_interval"]
        assert row["Cumulative H2 (g/t)"] == (
            pytest.approx(v["cumulative_h2_grams_per_ton"])
            if v["cumulative_h2_grams_per_ton"] is not None else None)
        assert row["Cumulative pore volumes"] == (
            pytest.approx(v["cumulative_pore_volumes"])
            if v["cumulative_pore_volumes"] is not None else None)
    hold = [r for r in rows if r["Experiment ID"] == "CFE_001-2"]
    assert [r["Hold interval"] for r in hold] == [True]


def test_conditions_additives_notes_summary(client, db_session, reporting_views):
    _seed_run(db_session)
    _resp, wb = _get(client, "CFE_001")

    _h, cond = _table(wb["Conditions"])
    assert [r["Experiment ID"] for r in cond] == [
        "CFE_001", "CFE_001-2", "CFE_001-2_Bypass1"]
    assert cond[0]["Rock mass (g)"] == 50.0
    assert cond[0]["Temperature (°C)"] == 90.0

    _h, adds = _table(wb["Additives"])
    view = _view(db_session, "SELECT * FROM v_chemical_additives"
                             " WHERE experiment_id = 'CFE_001'")
    assert len(adds) == len(view) == 1
    assert adds[0]["Compound"] == "CFE_NiCl2"
    assert adds[0]["Amount"] == 1.5
    assert adds[0]["Unit"] == view[0]["unit"]
    assert adds[0]["Mass (g)"] == pytest.approx(view[0]["mass_in_grams"])

    _h, notes = _table(wb["Notes"])
    view = _view(db_session,
                 "SELECT * FROM v_notes WHERE experiment_id LIKE 'CFE_001%'")
    assert {r["Note ID"] for r in notes} == {r["note_id"] for r in view}
    by_type = {r["Type"]: r for r in notes}
    assert by_type["result_note"]["Text"] == "cloudy"
    assert by_type["result_note"]["Author"] == "a@addisenergy.com"
    assert by_type["result_note"]["Result ID"] is not None
    assert by_type["description"]["Text"] == "Olivine core, Ni catalyst"

    summary = dict(list(wb["Summary"].iter_rows(values_only=True))[1:])
    assert summary["Base ID"] == "CFE_001"
    assert summary["Experiment IDs"] == "CFE_001, CFE_001-2, CFE_001-2_Bypass1"
    assert summary["Side samples (is_variant)"] == "CFE_001-2_Bypass1"
    assert summary["Description"] == "Olivine core, Ni catalyst"
    assert summary["Status"] == (
        "CFE_001: COMPLETED; CFE_001-2: ONGOING; CFE_001-2_Bypass1: COMPLETED")
    assert summary["Exported at"] == datetime(2026, 11, 6, 23, 30)
    assert summary["Exported by"] == "test@addisenergy.com"
    assert summary["Rows: Results"] == 4
    assert summary["Rows: Core Flood"] == 4
    assert summary["Rows: Conditions"] == 3
    assert summary["Rows: Additives"] == 1
    assert summary["Rows: Notes"] == 3


def test_experiment_without_results_keeps_headers(client, db_session, reporting_views):
    _experiment(db_session, "HPE_002", experiment_type="HPHT")
    _resp, wb = _get(client, "HPE_002")
    ws = wb["Results"]
    assert ws.max_row == 1
    headers = [c.value for c in ws[1]]
    assert headers[:3] == ["Experiment ID", "is_variant", "Result ID"]
    assert "H2 (ppm)" in headers


def test_experiment_without_base_id_exports_alone(db_session, reporting_views):
    exp = _experiment(db_session, "HPE_003", experiment_type="HPHT")
    exp.base_experiment_id = None
    db_session.flush()
    lineage = experiment_export.resolve_lineage(db_session, "HPE_003")
    assert lineage.base_id == "HPE_003"
    assert lineage.ids == ["HPE_003"]


def test_unknown_experiment_returns_404(client, db_session, reporting_views):
    resp = client.get("/api/experiments/NOPE_999/export")
    assert resp.status_code == 404


def test_export_is_read_only(client, db_session, reporting_views):
    _seed_run(db_session)
    before = db_session.execute(text(
        "SELECT count(*) FROM modifications_log")).scalar_one()
    _get(client, "CFE_001")
    after = db_session.execute(text(
        "SELECT count(*) FROM modifications_log")).scalar_one()
    assert after == before


def test_naive_utc_offset_check():
    """A Postgres timestamptz arrives aware; the cell is its lab wall clock."""
    aware = datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)
    assert experiment_export._cell(aware) == datetime(2026, 10, 2, 0, 0)


# ---------------------------------------------------------------------------
# Multi-experiment selection (issue #142): POST /api/experiments/export
# ---------------------------------------------------------------------------


def _post(client, ids, include_series=True):
    resp = client.post("/api/experiments/export", json={
        "experiment_ids": ids, "include_series": include_series})
    assert resp.status_code == 200, resp.text
    return resp, load_workbook(io.BytesIO(resp.content))


def _seed_vials(db):
    """Serum vials -t1/-t3/-t7 of one stem, plus the sequential re-run -2."""
    vials = []
    for exp_id, day in (("SERUM_X_001-t1", 1.0), ("SERUM_X_001-t3", 3.0),
                        ("SERUM_X_001-t7", 7.0), ("SERUM_X_001-2", 2.0)):
        exp = _experiment(db, exp_id, experiment_type="HPHT")
        _sample(db, exp, day, measured=_lab(2026, 10, 3))
        vials.append(exp)
    assert vials[3].base_experiment_id == "SERUM_X_001"
    return vials


def _summary(wb):
    _h, rows = _table(wb["Summary"])
    return {r["Field"]: r["Value"] for r in rows}


def test_selection_mixed_matches_views(client, db_session, reporting_views):
    root, seg2, bypass = _seed_run(db_session)
    hp = _experiment(db_session, "HPE_010", experiment_type="HPHT")
    _sample(db_session, hp, 2.0, measured=_lab(2026, 10, 3), ph=6.5)
    resp, wb = _post(client, ["CFE_001-2", "HPE_010"])
    assert resp.headers["content-disposition"] == (
        'attachment; filename="data_export_2026-11-06.xlsx"')
    assert wb.sheetnames == ["Experiments", "Results", "Core Flood", "Conditions",
                             "Additives", "Notes", "Summary"]
    _h, exps = _table(wb["Experiments"])
    assert [r["Experiment ID"] for r in exps] == [
        "CFE_001", "CFE_001-2", "CFE_001-2_Bypass1", "HPE_010"]
    assert [r["is_variant"] for r in exps] == [False, False, True, False]
    assert exps[3]["Experiment type"] == "HPHT"
    assert exps[0]["Description"] == "Olivine core, Ni catalyst"
    fks = [root.id, seg2.id, bypass.id, hp.id]
    view = {r["result_id"]: r for r in _view(
        db_session, "SELECT * FROM v_results_scalar WHERE experiment_fk = ANY(:f)",
        f=fks)}
    _h, rows = _table(wb["Results"])
    assert {r["Result ID"] for r in rows} == set(view)
    assert [r["Experiment ID"] for r in rows][-1] == "HPE_010"
    for r in rows:
        assert r["pH"] == pytest.approx(view[r["Result ID"]]["final_ph"])
    _h, cf = _table(wb["Core Flood"])
    assert {r["Experiment ID"] for r in cf} == {
        "CFE_001", "CFE_001-2", "CFE_001-2_Bypass1"}


def test_selection_without_series_exports_exact_picks(
        client, db_session, reporting_views):
    _seed_run(db_session)
    _resp, wb = _post(client, ["CFE_001-2"], include_series=False)
    _h, exps = _table(wb["Experiments"])
    assert [r["Experiment ID"] for r in exps] == ["CFE_001-2"]
    _h, rows = _table(wb["Results"])
    assert {r["Experiment ID"] for r in rows} == {"CFE_001-2"}
    assert _summary(wb)["Include whole series"] == "No"


def test_selection_stem_expands_vials_without_series(
        client, db_session, reporting_views):
    _seed_vials(db_session)
    _resp, wb = _post(client, ["SERUM_X_001-t1"], False)
    _h, exps = _table(wb["Experiments"])
    assert [r["Experiment ID"] for r in exps] == [
        "SERUM_X_001-t1", "SERUM_X_001-t3", "SERUM_X_001-t7"]
    _resp, wb = _post(client, ["SERUM_X_001-t1"], True)
    _h, exps = _table(wb["Experiments"])
    assert [r["Experiment ID"] for r in exps] == [
        "SERUM_X_001-2", "SERUM_X_001-t1", "SERUM_X_001-t3", "SERUM_X_001-t7"]


def test_selection_overlapping_picks_dedupe(client, db_session, reporting_views):
    _seed_run(db_session)
    _resp, wb = _post(client, ["CFE_001", "CFE_001-2", "CFE_001-2"])
    _h, exps = _table(wb["Experiments"])
    assert len(exps) == 3
    _h, rows = _table(wb["Results"])
    ids = [r["Result ID"] for r in rows]
    assert len(ids) == len(set(ids)) == 4


def test_selection_hpht_only_has_no_core_flood_tab(
        client, db_session, reporting_views):
    hp = _experiment(db_session, "HPE_010", experiment_type="HPHT")
    _sample(db_session, hp, 2.0)
    _resp, wb = _post(client, ["HPE_010"])
    assert wb.sheetnames == ["Experiments", "Results", "Conditions", "Additives",
                             "Notes", "Summary"]


def test_selection_experiment_without_conditions(
        client, db_session, reporting_views):
    _seed_run(db_session)
    bare = Experiment(experiment_id="BARE_001", experiment_number=next(_NUM),
                      status=ExperimentStatus.ONGOING)
    db_session.add(bare)
    db_session.flush()
    _resp, wb = _post(client, ["CFE_001", "BARE_001"])
    _h, exps = _table(wb["Experiments"])
    by_id = {r["Experiment ID"]: r for r in exps}
    assert set(by_id) == {"BARE_001", "CFE_001", "CFE_001-2", "CFE_001-2_Bypass1"}
    assert by_id["BARE_001"]["Experiment type"] is None
    _h, cond = _table(wb["Conditions"])
    assert {r["Experiment ID"] for r in cond} == {
        "CFE_001", "CFE_001-2", "CFE_001-2_Bypass1"}


def test_selection_unknown_ids_422(client, db_session, reporting_views):
    _seed_run(db_session)
    resp = client.post("/api/experiments/export", json={
        "experiment_ids": ["CFE_001", "NOPE_1", "NOPE_2"]})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Unknown experiment IDs: NOPE_1, NOPE_2"


def test_selection_cap_422(client, db_session, reporting_views, monkeypatch):
    monkeypatch.setattr(experiment_export, "EXPORT_MAX_EXPERIMENTS", 2)
    _seed_run(db_session)
    resp = client.post("/api/experiments/export", json={
        "experiment_ids": ["CFE_001"]})
    assert resp.status_code == 422
    assert resp.json()["detail"] == (
        "Export too large: 3 experiments after expansion (limit 2). "
        "Narrow the selection or turn off Include whole series.")


def test_selection_empty_list_422(client, db_session, reporting_views):
    resp = client.post("/api/experiments/export", json={"experiment_ids": []})
    assert resp.status_code == 422


def test_selection_summary(client, db_session, reporting_views):
    _seed_run(db_session)
    hp = _experiment(db_session, "HPE_010", experiment_type="HPHT")
    _sample(db_session, hp, 2.0)
    _resp, wb = _post(client, ["CFE_001", "HPE_010"])
    summary = _summary(wb)
    assert summary["Experiment count"] == 4
    assert summary["Series count"] == 2
    assert summary["Base IDs"] == "CFE_001, HPE_010"
    assert summary["Include whole series"] == "Yes"
    assert summary["Side samples (is_variant)"] == "CFE_001-2_Bypass1"
    assert summary["Exported at"] == datetime(2026, 11, 6, 23, 30)
    assert summary["Exported by"] == "test@addisenergy.com"
    assert summary["Rows: Experiments"] == 4
    assert summary["Rows: Results"] == 5


def test_vials_sort_by_timepoint_not_text(client, db_session, reporting_views):
    same_day = _lab(2026, 10, 1)
    for exp_id, day in (("SERUM_Y_001-t20", 20.0), ("SERUM_Y_001-t1", 1.0),
                        ("SERUM_Y_001-t3", 3.0)):
        exp = _experiment(db_session, exp_id, date_=same_day,
                          experiment_type="HPHT")
        assert exp.base_experiment_id == "SERUM_Y_001"
        _sample(db_session, exp, day, measured=_lab(2026, 10, 3))
    want = ["SERUM_Y_001-t1", "SERUM_Y_001-t3", "SERUM_Y_001-t20"]

    _resp, wb = _post(client, ["SERUM_Y_001-t1"], include_series=False)
    _h, exps = _table(wb["Experiments"])
    assert [r["Experiment ID"] for r in exps] == want
    _h, rows = _table(wb["Results"])
    assert [r["Experiment ID"] for r in rows] == want

    _resp, wb = _get(client, "SERUM_Y_001-t3")
    _h, rows = _table(wb["Results"])
    assert [r["Experiment ID"] for r in rows] == want
    _h, cond = _table(wb["Conditions"])
    assert [r["Experiment ID"] for r in cond] == want


def test_selection_more_than_500_ids_gets_string_detail(
        client, db_session, reporting_views):
    resp = client.post("/api/experiments/export", json={
        "experiment_ids": [f"NOPE_{i}" for i in range(501)]})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, str)
    assert detail.startswith("Unknown experiment IDs: ")


# ---------------------------------------------------------------------------
# XRD tabs: post-reaction XRD (v_experiment_xrd) and starting-rock XRD
# (v_sample_xrd), one wide row per timepoint / analysis.
# ---------------------------------------------------------------------------

def _xrd(db, exp, day, phases, *, rwp, measured):
    for mineral, amount in phases.items():
        db.add(XRDPhase(experiment_fk=exp.id, experiment_id=exp.experiment_id,
                        time_post_reaction_days=day, mineral_name=mineral,
                        amount=amount, rwp=rwp, measurement_date=measured))
    db.flush()


def _rock_xrd(db, sample_id, phases, *, analysis_date=None, lab="ActLabs",
              analyst="J. Doe"):
    if db.get(SampleInfo, sample_id) is None:
        db.add(SampleInfo(sample_id=sample_id))
        db.flush()
    ea = ExternalAnalysis(sample_id=sample_id, analysis_type="XRD",
                          analysis_date=analysis_date, laboratory=lab, analyst=analyst)
    db.add(ea)
    db.flush()
    for mineral, amount in phases.items():
        db.add(XRDPhase(sample_id=sample_id, external_analysis_id=ea.id,
                        mineral_name=mineral, amount=amount))
    db.flush()


def _seed_run_with_xrd(db):
    root, seg2, bypass = _seed_run(db)
    _xrd(db, root, 0, {"Forsterite": 60.0, "Lizardite": 30.0},
         rwp=2.5, measured=_lab(2026, 10, 1))
    _xrd(db, seg2, 10, {"Forsterite": 52.0, "Magnetite": 4.0, "Lizardite": 33.0},
         rwp=3.1, measured=_lab(2026, 10, 11))
    _rock_xrd(db, "CFE_ROCK_1", {"Forsterite": 61.9, "Amphibole": 6.3},
              analysis_date=_lab(2026, 9, 1))
    root.sample_id = "CFE_ROCK_1"
    seg2.sample_id = "CFE_ROCK_1"
    db.flush()
    return root, seg2, bypass


def test_xrd_tabs_follow_core_flood(client, db_session, reporting_views):
    _seed_run_with_xrd(db_session)
    _resp, wb = _get(client, "CFE_001")
    assert wb.sheetnames == ["Results", "Core Flood", "XRD", "Rock XRD", "Conditions",
                             "Additives", "Notes", "Summary"]
    summary = _summary(wb)
    assert summary["Rows: XRD"] == 2
    assert summary["Rows: Rock XRD"] == 1


def test_xrd_tab_is_wide_and_matches_view(client, db_session, reporting_views):
    _seed_run_with_xrd(db_session)
    _resp, wb = _get(client, "CFE_001-2")
    headers, rows = _table(wb["XRD"])
    # Minerals present anywhere in the export, alphabetical, after the fixed columns.
    assert headers == ["Experiment ID", "is_variant", "Day", "Measurement date", "Rwp",
                       "Forsterite (%)", "Lizardite (%)", "Magnetite (%)"]
    assert [(r["Experiment ID"], r["Day"]) for r in rows] == [
        ("CFE_001", 0), ("CFE_001-2", 10)]
    view = {(v["experiment_id"], v["mineral_name"]): v for v in _view(
        db_session, "SELECT * FROM v_experiment_xrd"
                    " WHERE experiment_id IN ('CFE_001', 'CFE_001-2')")}
    seg = rows[1]
    assert seg["is_variant"] is False
    assert seg["Forsterite (%)"] == view[("CFE_001-2", "Forsterite")]["amount_pct"] == 52.0
    assert seg["Magnetite (%)"] == 4.0
    assert seg["Rwp"] == pytest.approx(3.1)
    assert seg["Measurement date"] == _naive_lab(view[("CFE_001-2", "Magnetite")]
                                                 ["measurement_date"])
    # A mineral not measured at a timepoint is blank, not 0.
    assert rows[0]["Magnetite (%)"] is None


def test_rock_xrd_tab_names_the_experiments_using_the_sample(
        client, db_session, reporting_views):
    _seed_run_with_xrd(db_session)
    _resp, wb = _get(client, "CFE_001")
    headers, rows = _table(wb["Rock XRD"])
    assert headers == ["Sample ID", "Used by", "Analysis date", "Laboratory", "Analyst",
                       "Amphibole (%)", "Forsterite (%)"]
    assert len(rows) == 1
    assert rows[0]["Sample ID"] == "CFE_ROCK_1"
    assert rows[0]["Used by"] == "CFE_001, CFE_001-2"
    assert rows[0]["Analysis date"] == datetime(2026, 9, 1)
    assert rows[0]["Laboratory"] == "ActLabs"
    assert rows[0]["Forsterite (%)"] == 61.9
    assert rows[0]["Amphibole (%)"] == 6.3


def test_post_reaction_xrd_never_counts_as_rock_xrd(
        client, db_session, reporting_views):
    """An experiment's own XRD stays off Rock XRD even when it has a sample ID."""
    exp = _experiment(db_session, "HPE_020", experiment_type="HPHT")
    db_session.add(SampleInfo(sample_id="HPE_ROCK_2"))
    db_session.flush()
    exp.sample_id = "HPE_ROCK_2"
    _xrd(db_session, exp, 7, {"Talc": 12.0}, rwp=4.0, measured=_lab(2026, 10, 8))
    _resp, wb = _get(client, "HPE_020")
    assert wb.sheetnames == ["Results", "XRD", "Conditions", "Additives", "Notes",
                             "Summary"]


def test_selection_includes_xrd_tabs(client, db_session, reporting_views):
    _seed_run_with_xrd(db_session)
    hp = _experiment(db_session, "HPE_010", experiment_type="HPHT")
    _sample(db_session, hp, 2.0)
    _rock_xrd(db_session, "HPE_ROCK_1", {"Quartz": 90.0})
    hp.sample_id = "HPE_ROCK_1"
    db_session.flush()
    _resp, wb = _post(client, ["CFE_001", "HPE_010"])
    assert wb.sheetnames == ["Experiments", "Results", "Core Flood", "XRD", "Rock XRD",
                             "Conditions", "Additives", "Notes", "Summary"]
    _h, rock = _table(wb["Rock XRD"])
    # Member order: the CFE series first, then HPE_010.
    assert [(r["Sample ID"], r["Used by"]) for r in rock] == [
        ("CFE_ROCK_1", "CFE_001, CFE_001-2"), ("HPE_ROCK_1", "HPE_010")]
    assert rock[0]["Quartz (%)"] is None
    assert rock[1]["Quartz (%)"] == 90.0
