from __future__ import annotations

import io
from typing import List, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from database import PXRFReading
from frontend.config.variable_config import PXRF_REQUIRED_COLUMNS
from utils.storage import get_file


NULL_EQUIVALENTS = ['', '<LOD', 'LOD', 'ND', 'n.d.', 'n/a', 'N/A', None]


class PXRFUploadService:
    @staticmethod
    def _load_excel_from_bytes(file_bytes: bytes) -> Tuple[pd.DataFrame, List[str]]:
        errors: List[str] = []
        try:
            df = pd.read_excel(io.BytesIO(file_bytes), engine='openpyxl')
        except Exception as e:
            return pd.DataFrame(), [f"Failed to read Excel: {e}"]

        missing = PXRF_REQUIRED_COLUMNS - set(df.columns)
        if missing:
            errors.append("Missing required columns: " + ", ".join(sorted(missing)))
            return pd.DataFrame(), errors
        return df, errors

    @staticmethod
    def _clean_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        errors: List[str] = []
        try:
            # Normalize Reading No: convert to string and remove .0 suffix from floats
            # Excel stores integers as floats (1 becomes 1.0), so "1.0" should become "1"
            df['Reading No'] = df['Reading No'].apply(
                lambda x: str(int(float(x))) if pd.notna(x) and str(x).replace('.', '', 1).replace('-', '', 1).isdigit() else str(x)
            ).str.strip()

            # Drop empty Reading No rows
            df = df.dropna(subset=['Reading No'])
            df = df[df['Reading No'] != '']

            # Clean numeric columns
            for col in PXRF_REQUIRED_COLUMNS - {'Reading No'}:
                df[col] = df[col].replace(NULL_EQUIVALENTS, 0)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        except Exception as e:
            errors.append(f"Error cleaning data: {e}")
        return df, errors

    @staticmethod
    def _upsert_dataframe(db: Session, df: pd.DataFrame, update_existing: bool) -> Tuple[int, int, int, List[str]]:
        inserted = updated = skipped = 0
        errors: List[str] = []
        try:
            existing_reading_nos = set(row[0] for row in db.query(PXRFReading.reading_no).all())
            for _, row in df.iterrows():
                reading_no = row['Reading No']
                reading_data = {
                    'reading_no': reading_no,
                    'fe': row['Fe'],
                    'mg': row['Mg'],
                    'ni': row['Ni'],
                    'cu': row['Cu'],
                    'si': row['Si'],
                    'co': row['Co'],
                    'mo': row['Mo'],
                    'al': row['Al'],
                    'ca': row['Ca'],
                    'k': row['K'],
                    'au': row['Au'],
                }

                if reading_no in existing_reading_nos:
                    if update_existing:
                        existing = db.query(PXRFReading).filter(PXRFReading.reading_no == reading_no).first()
                        for k, v in reading_data.items():
                            if k != 'reading_no':
                                setattr(existing, k, v)
                        updated += 1
                    else:
                        skipped += 1
                else:
                    db.add(PXRFReading(**reading_data))
                    inserted += 1
        except Exception as e:
            errors.append(f"Error during database upsert: {e}")
        return inserted, updated, skipped, errors

    @classmethod
    def ingest_from_bytes(cls, db: Session, file_bytes: bytes, update_existing: bool = False) -> Tuple[int, int, int, List[str]]:
        df, errors = cls._load_excel_from_bytes(file_bytes)
        if errors:
            return 0, 0, 0, errors
        df, clean_errors = cls._clean_dataframe(df)
        if clean_errors:
            return 0, 0, 0, clean_errors
        inserted, updated, skipped, upsert_errors = cls._upsert_dataframe(db, df, update_existing)
        return inserted, updated, skipped, upsert_errors

    @classmethod
    def ingest_from_source(cls, db: Session, file_source: str, update_existing: bool = False) -> Tuple[int, int, int, List[str]]:
        try:
            file_bytes = get_file(file_source)
        except Exception as e:
            return 0, 0, 0, [f"Error fetching file '{file_source}': {e}"]
        return cls.ingest_from_bytes(db, file_bytes, update_existing)


