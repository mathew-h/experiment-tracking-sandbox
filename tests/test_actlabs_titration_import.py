import io
import pandas as pd
import numpy as np

from database import SampleInfo, Analyte, ElementalAnalysis
from backend.services.bulk_uploads.actlabs_titration_data import ActlabsRockTitrationService


def _build_actlabs_like_csv_bytes():
    """Construct a minimal ActLabs-like table as CSV bytes with header rows.
    Rows:
      0: Report Number
      1: Report Date
      2: Analyte Symbol headers (including 'Sample ID')
      3: Units row
      4: Detection Limit
      5: Analysis Method
      6+: data rows
    """
    # Build a DataFrame with header rows matching service expectations
    # Columns: Sample ID | FeO | SiO2
    header_symbols = ["Sample ID", "FeO", "SiO2"]
    header_units = ["", "%", "%"]
    detection_limit = ["Detection Limit", "0.01", "0.01"]
    analysis_method = ["Analysis Method: titration", "", ""]

    data_rows = [
        ["Rock_1", 12.5, 45.0],
        ["Rock_2", 8.0, 50.0],
    ]

    # Assemble as a list of rows
    rows = [
        ["Report Number", "", ""],
        ["Report Date", "", ""],
        header_symbols,
        header_units,
        detection_limit,
        analysis_method,
        *data_rows,
    ]

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    # Write CSV with no header to mimic header=None read
    df.to_csv(buf, header=False, index=False)
    buf.seek(0)
    return buf.getvalue()


def test_actlabs_import_creates_analytes_and_results(test_db):
    # Arrange: add required samples
    for sid in ("Rock_1", "Rock_2"):
        test_db.add(SampleInfo(sample_id=sid))
    test_db.commit()

    payload = _build_actlabs_like_csv_bytes()

    # Act: run import
    created, updated, skipped, errors = ActlabsRockTitrationService.import_excel(test_db, payload)

    # Assert: no critical errors
    assert errors == [] or all(isinstance(e, str) for e in errors)
    # Expect two rows created (2 samples x at least one analyte)
    assert created >= 2

    # Verify analytes exist
    analytes = {a.analyte_symbol: a for a in test_db.query(Analyte).all()}
    assert "FeO" in analytes
    assert "SiO2" in analytes

    # Verify compositions inserted for both samples and both analytes
    results = test_db.query(ElementalAnalysis).all()
    by_key = {(r.sample_id, r.analyte_id): r for r in results}
    feo_id = analytes["FeO"].id
    sio2_id = analytes["SiO2"].id

    assert ("Rock_1", feo_id) in by_key
    assert ("Rock_1", sio2_id) in by_key
    assert ("Rock_2", feo_id) in by_key
    assert ("Rock_2", sio2_id) in by_key

    # Check values roughly match inputs
    assert by_key[("Rock_1", feo_id)].analyte_composition == 12.5
    assert by_key[("Rock_1", sio2_id)].analyte_composition == 45.0
    assert by_key[("Rock_2", feo_id)].analyte_composition == 8.0
    assert by_key[("Rock_2", sio2_id)].analyte_composition == 50.0


