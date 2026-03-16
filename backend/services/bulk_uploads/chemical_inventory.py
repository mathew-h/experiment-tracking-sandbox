from __future__ import annotations

import io
from typing import List, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from database import Compound


class ChemicalInventoryService:
    @staticmethod
    def bulk_upsert_from_excel(db: Session, file_bytes: bytes) -> Tuple[int, int, int, List[str]]:
        """
        Upsert compounds from an Excel file using the same columns as the existing UI template.
        Returns (created, updated, skipped, errors).
        """
        created = updated = skipped = 0
        errors: List[str] = []

        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            return 0, 0, 0, [f"Failed to read Excel: {e}"]

        # Normalize column names (case-insensitive match to template)
        col_map = {str(c).lower().strip(): str(c) for c in df.columns}
        required = {"name"}
        if not required.issubset(set(col_map.keys())):
            return 0, 0, 0, ["Missing required column(s): name"]

        template_columns = [
            "name", "formula", "cas_number", "molecular_weight", "density",
            "melting_point", "boiling_point", "solubility", "hazard_class",
            "supplier", "catalog_number", "notes",
        ]

        # Reindex to expected columns (optional ones may be absent)
        normalized_cols = [c for c in template_columns if c in col_map]
        df = df.rename(columns={col_map[c]: c for c in normalized_cols if c in col_map})

        def num(val):
            try:
                return float(val)
            except Exception:
                return None

        for idx, row in df.iterrows():
            try:
                name = str(row.get("name") or "").strip()
                if not name:
                    skipped += 1
                    continue

                formula = str(row.get("formula")) if pd.notna(row.get("formula")) else None
                cas_number = str(row.get("cas_number")) if pd.notna(row.get("cas_number")) else None
                molecular_weight = num(row.get("molecular_weight"))
                density = num(row.get("density"))
                melting_point = num(row.get("melting_point"))
                boiling_point = num(row.get("boiling_point"))
                solubility = str(row.get("solubility")) if pd.notna(row.get("solubility")) else None
                hazard_class = str(row.get("hazard_class")) if pd.notna(row.get("hazard_class")) else None
                supplier = str(row.get("supplier")) if pd.notna(row.get("supplier")) else None
                catalog_number = str(row.get("catalog_number")) if pd.notna(row.get("catalog_number")) else None
                notes = str(row.get("notes")) if pd.notna(row.get("notes")) else None

                existing = db.query(Compound).filter(Compound.name.ilike(name)).first()
                if not existing and cas_number:
                    existing = db.query(Compound).filter(Compound.cas_number == cas_number).first()

                if existing:
                    existing.formula = formula or existing.formula
                    existing.cas_number = cas_number or existing.cas_number
                    existing.molecular_weight = molecular_weight if molecular_weight is not None else existing.molecular_weight
                    existing.density = density if density is not None else existing.density
                    existing.melting_point = melting_point if melting_point is not None else existing.melting_point
                    existing.boiling_point = boiling_point if boiling_point is not None else existing.boiling_point
                    existing.solubility = solubility or existing.solubility
                    existing.hazard_class = hazard_class or existing.hazard_class
                    existing.supplier = supplier or existing.supplier
                    existing.catalog_number = catalog_number or existing.catalog_number
                    existing.notes = notes or existing.notes
                    updated += 1
                else:
                    comp = Compound(
                        name=name,
                        formula=formula,
                        cas_number=cas_number,
                        molecular_weight=molecular_weight,
                        density=density,
                        melting_point=melting_point,
                        boiling_point=boiling_point,
                        solubility=solubility,
                        hazard_class=hazard_class,
                        supplier=supplier,
                        catalog_number=catalog_number,
                        notes=notes,
                    )
                    db.add(comp)
                    created += 1
            except Exception as e:
                errors.append(f"Row {idx+2}: {e}")

        return created, updated, skipped, errors


