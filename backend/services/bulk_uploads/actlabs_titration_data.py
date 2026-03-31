from __future__ import annotations

import io
import math
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from database import Analyte, ElementalAnalysis, SampleInfo
from database.models.analysis import ExternalAnalysis


def _normalize_sample_id(sample_id: str) -> str:
    """Normalize a sample ID for fuzzy matching: lowercase, remove all non-alphanumeric characters."""
    return re.sub(r"[^a-z0-9]", "", sample_id.lower())


def _fuzzy_find_sample(db: Session, raw_sample_id: str) -> Optional[SampleInfo]:
    """Find a SampleInfo by normalized sample_id (case-insensitive, symbols ignored).

    Tries exact match first; falls back to normalizing both sides.
    Returns the first match or None.
    """
    sample = db.query(SampleInfo).filter(SampleInfo.sample_id == raw_sample_id).first()
    if sample:
        return sample
    normalized_input = _normalize_sample_id(raw_sample_id)
    all_samples = db.query(SampleInfo).all()
    for s in all_samples:
        if _normalize_sample_id(s.sample_id) == normalized_input:
            return s
    return None


def _write_elemental_record(
    db: Session,
    ext_analysis_id: int,
    sample_id: str,
    analyte: "Analyte",
    value: float,
    overwrite: bool,
) -> "Tuple[int, int]":
    """Write a single ElementalAnalysis record. Returns (created_delta, updated_delta).

    When overwrite=False, any existing record is preserved and (0, 0) is returned.
    When overwrite=True, any existing record is updated and (0, 1) is returned.
    Null/blank values must never be passed to this function.
    """
    existing = (
        db.query(ElementalAnalysis)
        .filter(
            ElementalAnalysis.external_analysis_id == ext_analysis_id,
            ElementalAnalysis.analyte_id == analyte.id,
        )
        .first()
    )
    if existing:
        if overwrite:
            existing.analyte_composition = value
            return 0, 1
        return 0, 0
    db.add(ElementalAnalysis(
        external_analysis_id=ext_analysis_id,
        sample_id=sample_id,
        analyte_id=analyte.id,
        analyte_composition=value,
    ))
    return 1, 0


class AnalyteService:
    @staticmethod
    def bulk_upsert_from_excel(db: Session, file_bytes: bytes) -> Tuple[int, int, int, List[str]]:
        """
        Upsert analyte definitions from an Excel file with columns: analyte_symbol*, unit*.
        Returns (created, updated, skipped, errors).
        """
        errors: List[str] = []
        created = updated = skipped = 0

        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            return 0, 0, 0, [f"Failed to read Excel: {e}"]

        df.columns = [str(c).strip().lower() for c in df.columns]
        required = {"analyte_symbol", "unit"}
        if not required.issubset(set(df.columns)):
            return 0, 0, 0, [f"Missing required columns: {', '.join(sorted(required - set(df.columns)))}"]

        for idx, row in df.iterrows():
            try:
                symbol = str(row.get("analyte_symbol") or "").strip()
                unit = str(row.get("unit") or "").strip()
                if not symbol or not unit:
                    skipped += 1
                    continue

                existing = db.query(Analyte).filter(Analyte.analyte_symbol.ilike(symbol)).first()
                if existing:
                    existing.unit = unit
                    updated += 1
                else:
                    db.add(Analyte(analyte_symbol=symbol, unit=unit))
                    created += 1
            except Exception as e:
                errors.append(f"Row {idx+2}: {e}")

        return created, updated, skipped, errors


class ElementalCompositionService:
    @staticmethod
    def bulk_upsert_wide_from_excel(
        db: Session,
        file_bytes: bytes,
        default_unit: Optional[str] = None,
        overwrite: bool = False,
    ) -> Tuple[int, int, int, List[str]]:
        """
        Upsert ElementalAnalysis from a wide Excel file:
          - First column: sample_id
          - Remaining columns: analyte symbols
          - Cells: numeric composition

        If ``default_unit`` is provided, any analyte header not already in the
        Analyte table is auto-created with that unit.  When ``default_unit`` is
        None (the default), unknown analyte headers are silently skipped.

        Returns (created, updated, skipped_rows, errors).
        """
        errors: List[str] = []
        created = updated = skipped = 0
        affected_sample_ids: set[str] = set()

        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            return 0, 0, 0, [f"Failed to read Excel: {e}"]

        df.columns = [str(c).strip() for c in df.columns]
        sample_col = None
        for c in df.columns:
            if c.lower() == "sample_id":
                sample_col = c
                break
        if not sample_col:
            return 0, 0, 0, ["First column must be 'sample_id'."]

        analyte_headers = [c for c in df.columns if c != sample_col]
        if not analyte_headers:
            return 0, 0, 0, ["No analyte columns detected."]

        all_analytes = db.query(Analyte).all()
        symbol_to_analyte = {a.analyte_symbol.lower(): a for a in all_analytes}

        # Auto-create analytes for unknown headers when default_unit is supplied
        if default_unit:
            for symbol in analyte_headers:
                sym_lower = str(symbol).lower()
                if sym_lower not in symbol_to_analyte:
                    new_analyte = Analyte(analyte_symbol=symbol, unit=default_unit)
                    db.add(new_analyte)
                    db.flush()  # assign id before loop uses it
                    symbol_to_analyte[sym_lower] = new_analyte

        # Cache ExternalAnalysis stubs per sample_id to avoid repeated queries
        ext_analysis_cache: Dict[str, int] = {}

        def _get_or_create_ext_analysis(sample_id: str) -> int:
            """Return the id of a 'Bulk Elemental Composition' ExternalAnalysis stub for this sample."""
            if sample_id in ext_analysis_cache:
                return ext_analysis_cache[sample_id]
            stub = (
                db.query(ExternalAnalysis)
                .filter(
                    ExternalAnalysis.sample_id == sample_id,
                    ExternalAnalysis.analysis_type == "Bulk Elemental Composition",
                )
                .first()
            )
            if not stub:
                stub = ExternalAnalysis(
                    sample_id=sample_id,
                    analysis_type="Bulk Elemental Composition",
                )
                db.add(stub)
                db.flush()
            ext_analysis_cache[sample_id] = stub.id
            return stub.id

        for idx, row in df.iterrows():
            try:
                sample_id = str(row.get(sample_col) or '').strip()
                if not sample_id:
                    skipped += 1
                    continue

                # Ensure sample exists (fuzzy: case-insensitive, symbols stripped)
                sample = _fuzzy_find_sample(db, sample_id)
                if not sample:
                    errors.append(f"Row {idx+2}: sample_id '{sample_id}' not found")
                    continue
                canonical_id = sample.sample_id
                affected_sample_ids.add(canonical_id)

                ext_analysis_id = _get_or_create_ext_analysis(canonical_id)

                for symbol in analyte_headers:
                    analyte = symbol_to_analyte.get(str(symbol).lower())
                    if not analyte:
                        # Unknown analyte and no default_unit — skip silently
                        continue
                    val = row.get(symbol)
                    if val is None or (isinstance(val, float) and pd.isna(val)):
                        continue
                    try:
                        fval = float(val)
                    except Exception:
                        continue

                    delta_c, delta_u = _write_elemental_record(
                        db, ext_analysis_id, canonical_id, analyte, fval, overwrite
                    )
                    created += delta_c
                    updated += delta_u
            except Exception as e:
                errors.append(f"Row {idx+2}: {e}")

        if affected_sample_ids:
            from backend.services.elemental_composition_service import recalculate_conditions_for_samples
            recalculate_conditions_for_samples(db, affected_sample_ids)

        return created, updated, skipped, errors


class ActlabsRockTitrationService:
    """Parser and importer for ActLabs rock titration files (Excel or CSV)."""

    @staticmethod
    def _read_table_with_mode(file_bytes: bytes) -> Tuple[pd.DataFrame, Optional[str], Optional[str]]:
        """Read file and return (df, mode, error).
        mode is one of {"excel", "csv"} when successful.
        """
        try:
            df = pd.read_excel(io.BytesIO(file_bytes), header=None)
            return df, "excel", None
        except Exception:
            pass
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), header=None)
            return df, "csv", None
        except Exception as e:
            return pd.DataFrame(), None, f"Failed to read file as Excel or CSV: {e}"

    @staticmethod
    def _read_table(file_bytes: bytes) -> Tuple[pd.DataFrame, Optional[str]]:
        """Try reading as Excel first, then CSV; always return a headerless table (header=None)."""
        try:
            df = pd.read_excel(io.BytesIO(file_bytes), header=None)
            return df, None
        except Exception:
            pass
        try:
            # Read CSV without headers
            df = pd.read_csv(io.BytesIO(file_bytes), header=None)
            return df, None
        except Exception as e:
            return pd.DataFrame(), f"Failed to read file as Excel or CSV: {e}"

    @staticmethod
    def _detect_sample_id_col(df_raw: pd.DataFrame) -> int:
        search_rows = min(6, len(df_raw))
        for c in range(df_raw.shape[1]):
            vals = df_raw.iloc[:search_rows, c].astype(str).str.lower().tolist()
            if any((("sample" in v and "id" in v) or v.strip() == "sample_id") for v in vals):
                return c
        return 0

    @staticmethod
    def _extract_last_analyte_map(df_raw: pd.DataFrame, sample_id_col: int) -> Dict[str, Tuple[int, Optional[str]]]:
        row3 = df_raw.iloc[2, :]  # Analyte Symbol
        row4 = df_raw.iloc[3, :]  # unit
        symbol_to_col_unit: Dict[str, Tuple[int, Optional[str]]] = {}
        for c in range(df_raw.shape[1]):
            if c == sample_id_col:
                continue
            symbol = row3[c]
            if pd.isna(symbol):
                continue
            sym = str(symbol).strip()
            if not sym:
                continue
            unit = None
            if c < len(row4):
                u = row4[c]
                unit = None if pd.isna(u) else str(u).strip() or None
            # Overwrite previous occurrence so the last column wins
            symbol_to_col_unit[sym] = (c, unit)
        return symbol_to_col_unit

    @staticmethod
    def _find_data_start_index(df_raw: pd.DataFrame) -> int:
        """Heuristically find the first data row index (after the header/meta rows).
        For ActLabs CSV, rows typically are:
          0: Report Number
          1: Report Date
          2: Analyte Symbol (headers row)
          3: Unit Symbol
          4: Detection Limit
          5: Analysis Method
          6+: data rows
        We prefer the row after 'Analysis Method'. Fallback to 4.
        """
        max_scan = min(12, len(df_raw))
        for i in range(max_scan):
            try:
                first_cell = str(df_raw.iat[i, 0]).strip().lower()
            except Exception:
                first_cell = ""
            if first_cell.startswith("analysis method"):
                return i + 1
        # Fallback to prior assumption (Excel layout)
        return 4

    @staticmethod
    def _coerce_number(x) -> Tuple[Optional[float], Optional[str]]:
        if pd.isna(x):
            return None, None
        sx = str(x).strip()
        if sx == "":
            return None, None
        if sx.lower() in {"nd", "na", "n/a"}:
            return None, sx
        try:
            val = float(sx)
            if math.isfinite(val):
                return val, None
        except ValueError:
            pass
        try:
            val2 = float(sx.lstrip("<>").strip())
            return val2, sx if sx and sx[0] in "<>" else sx
        except Exception:
            return None, sx

    @classmethod
    def diagnose(cls, file_bytes: bytes) -> Tuple[Dict[str, object], List[str]]:
        """Analyze file structure without touching the database.
        Returns (diagnostics, warnings).
        diagnostics keys:
          - read_mode: "excel"|"csv"
          - shape: (rows, cols)
          - sample_id_col: int
          - data_start_row: int
          - analytes: List[{symbol, unit, col_index}]
          - sample_id_preview: List[str]
          - analyte_value_quality: List[{symbol, numeric, blank, text, inspected_rows}]
        """
        diags: Dict[str, object] = {}
        warnings: List[str] = []

        df_raw, mode, err = cls._read_table_with_mode(file_bytes)
        if err:
            return {}, [err]
        if df_raw.empty:
            return {}, ["No data found."]

        diags["read_mode"] = mode
        diags["shape"] = (int(df_raw.shape[0]), int(df_raw.shape[1]))

        try:
            sample_id_col = cls._detect_sample_id_col(df_raw)
        except Exception as e:
            return {}, [f"Failed to detect sample_id column: {e}"]
        diags["sample_id_col"] = int(sample_id_col)
        if sample_id_col == 0:
            warnings.append("Sample ID column auto-defaulted to column 0; header not clearly detected.")

        try:
            analyte_map = cls._extract_last_analyte_map(df_raw, sample_id_col)
        except Exception as e:
            return {}, [f"Failed to parse analyte headers: {e}"]
        analytes_list = [
            {"symbol": sym, "unit": unit, "col_index": int(col)}
            for sym, (col, unit) in analyte_map.items()
        ]
        diags["analytes"] = sorted(analytes_list, key=lambda x: x["col_index"]) if analytes_list else []
        if not analytes_list:
            warnings.append("No analyte columns detected (rows 3-4). Confirm report layout.")

        try:
            data_start = cls._find_data_start_index(df_raw)
        except Exception as e:
            return {}, [f"Failed to determine data start row: {e}"]
        diags["data_start_row"] = int(data_start)

        data = df_raw.iloc[data_start:, :].reset_index(drop=True)

        # Preview sample ids
        sample_ids: List[str] = []
        preview_rows = min(20, len(data))
        for i in range(preview_rows):
            try:
                sid_raw = data.iat[i, sample_id_col]
                sid = "" if pd.isna(sid_raw) else str(sid_raw).strip()
                if sid:
                    sample_ids.append(sid)
            except Exception:
                break
        diags["sample_id_preview"] = sample_ids[:10]
        if not diags["sample_id_preview"]:
            warnings.append("No sample IDs found in the first rows after headers.")

        # Inspect value quality for first N rows
        quality_rows = min(50, len(data))
        quality: List[Dict[str, object]] = []
        for sym, (col_idx, _unit) in analyte_map.items():
            numeric = blank = text = 0
            for i in range(quality_rows):
                if col_idx >= data.shape[1]:
                    break
                cell = data.iat[i, col_idx]
                if pd.isna(cell) or str(cell).strip() == "":
                    blank += 1
                    continue
                vnum, vtxt = cls._coerce_number(cell)
                if vnum is not None:
                    numeric += 1
                else:
                    text += 1
            quality.append({
                "symbol": sym,
                "numeric": int(numeric),
                "blank": int(blank),
                "text": int(text),
                "inspected_rows": int(quality_rows),
            })
        diags["analyte_value_quality"] = quality

        return diags, warnings

    @classmethod
    def import_excel(cls, db: Session, file_bytes: bytes, overwrite: bool = False) -> Tuple[int, int, int, List[str]]:
        """
        Import ActLabs Excel to normalized tables.
        - Upserts analytes (last header wins for units)
        - Upserts results per (sample_id, analyte_id)
        Returns (results_created, results_updated, skipped_rows, errors)
        """
        errors: List[str] = []
        results_created = results_updated = skipped = 0

        df_raw, read_err = cls._read_table(file_bytes)
        if read_err:
            return 0, 0, 0, [read_err]
        if df_raw.empty:
            return 0, 0, 0, ["No data found."]

        sample_id_col = cls._detect_sample_id_col(df_raw)
        symbol_to_col_unit = cls._extract_last_analyte_map(df_raw, sample_id_col)

        # Note: a defaulted sample_id_col (0) is not a fatal error if data imports correctly
        if not symbol_to_col_unit:
            errors.append("No analyte columns detected; ensure rows 3-4 contain analyte and unit headers.")

        # Data rows typically start after the 'Analysis Method' row
        data_start = cls._find_data_start_index(df_raw)
        data = df_raw.iloc[data_start:, :].reset_index(drop=True)

        # Upsert analytes (last column wins for unit)
        for sym, (_c, unit) in symbol_to_col_unit.items():
            existing = db.query(Analyte).filter(Analyte.analyte_symbol.ilike(sym)).first()
            if existing:
                if unit:
                    existing.unit = unit
            else:
                db.add(Analyte(analyte_symbol=sym, unit=unit or "ppm"))

        # Preload analyte ids
        all_analytes = db.query(Analyte).all()
        symbol_to_analyte = {a.analyte_symbol.lower(): a for a in all_analytes}

        # Cache ExternalAnalysis stubs per sample_id (same pattern as ElementalCompositionService)
        ext_analysis_cache: dict[str, int] = {}

        def _get_ext_analysis_id(sid: str) -> int:
            if sid in ext_analysis_cache:
                return ext_analysis_cache[sid]
            stub = (
                db.query(ExternalAnalysis)
                .filter_by(sample_id=sid, analysis_type="Elemental")
                .first()
            )
            if not stub:
                stub = ExternalAnalysis(sample_id=sid, analysis_type="Elemental")
                db.add(stub)
                db.flush()
            ext_analysis_cache[sid] = stub.id
            return stub.id

        # Iterate rows
        for i in range(len(data)):
            sid_raw = data.iat[i, sample_id_col]
            if pd.isna(sid_raw):
                continue
            sample_id = str(sid_raw).strip()
            if not sample_id:
                continue
            # ensure sample exists (fuzzy: case-insensitive, symbols stripped)
            sample = _fuzzy_find_sample(db, sample_id)
            if not sample:
                errors.append(f"Row {i+5}: sample_id '{sample_id}' not found")
                continue
            canonical_id = sample.sample_id

            for sym, (col_idx, _unit) in symbol_to_col_unit.items():
                if col_idx >= data.shape[1]:
                    continue
                cell = data.iat[i, col_idx]
                vnum, _vtext = cls._coerce_number(cell)
                if vnum is None:
                    continue
                analyte = symbol_to_analyte.get(sym.lower())
                if not analyte:
                    # If misaligned, skip
                    continue
                ext_id = _get_ext_analysis_id(canonical_id)
                delta_c, delta_u = _write_elemental_record(
                    db, ext_id, canonical_id, analyte, vnum, overwrite
                )
                results_created += delta_c
                results_updated += delta_u

        return results_created, results_updated, skipped, errors


