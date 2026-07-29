from __future__ import annotations

import io
from typing import List, Tuple

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import Experiment, ExperimentalConditions, ChemicalAdditive, Compound, AmountUnit
from backend.services.calculations.registry import recalculate
from database.models.chemicals import ADDITION_METHOD_MAX_LENGTH


class ExperimentAdditivesService:
    @staticmethod
    def bulk_upsert_from_excel(db: Session, file_bytes: bytes) -> Tuple[int, int, int, List[str]]:
        """
        Upsert experiment additives from Excel, without delete/replace behavior.
        Columns: experiment_id*, compound*, amount*, unit*, order (opt), method (opt)
        Returns (created, updated, skipped, errors).
        """
        created = updated = skipped = 0
        errors: List[str] = []

        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            return 0, 0, 0, [f"Failed to read Excel: {e}"]

        # Normalize headers (strip asterisks used to indicate required in templates)
        df.columns = [str(c).replace('*', '').strip().lower() for c in df.columns]
        required_cols = {'experiment_id', 'compound', 'amount', 'unit'}
        if not required_cols.issubset(set(df.columns)):
            missing = ', '.join(sorted(required_cols - set(df.columns)))
            return 0, 0, 0, [f"Missing required columns: {missing}"]

        # Preload compound lookup (case-insensitive)
        all_compounds = db.query(Compound).all()
        name_to_compound = {c.name.lower(): c for c in all_compounds}

        for idx, row in df.iterrows():
            # Per-row savepoint isolation (issue #96 Defect B): a failed flush or recalculation
            # anywhere in this row's processing is confined to its own SAVEPOINT and rolled back,
            # leaving the session usable for the remaining rows.
            savepoint = db.begin_nested()
            row_ok = False
            try:
                exp_id = str(row.get('experiment_id') or '').strip()
                comp_name = str(row.get('compound') or '').strip()
                unit_val = str(row.get('unit') or '').strip()
                amount_val = row.get('amount')
                order_val = row.get('order') if 'order' in df.columns else None
                method_val = row.get('method') if 'method' in df.columns else None

                if not exp_id or not comp_name or not unit_val:
                    skipped += 1
                    continue

                try:
                    amount_float = float(amount_val)
                except Exception:
                    errors.append(f"Row {idx+2}: invalid amount '{amount_val}'")
                    continue
                if amount_float <= 0:
                    errors.append(f"Row {idx+2}: amount must be > 0")
                    continue

                # Validate unit
                unit_enum = None
                for u in AmountUnit:
                    if u.value == unit_val:
                        unit_enum = u
                        break
                if unit_enum is None:
                    errors.append(f"Row {idx+2}: invalid unit '{unit_val}'")
                    continue

                # Resolve experiment
                exp_id_norm = ''.join(ch for ch in exp_id.lower() if ch not in ['-', '_', ' '])
                experiment = db.query(Experiment).filter(
                    func.lower(
                        func.replace(
                            func.replace(
                                func.replace(Experiment.experiment_id, '-', ''),
                                '_', ''
                            ),
                            ' ', ''
                        )
                    ) == exp_id_norm
                ).first()
                if not experiment:
                    errors.append(f"Row {idx+2}: experiment_id '{exp_id}' not found")
                    continue

                # Resolve or create ExperimentalConditions for this experiment
                conditions = db.query(ExperimentalConditions).filter(ExperimentalConditions.experiment_fk == experiment.id).first()
                if not conditions:
                    conditions = ExperimentalConditions(
                        experiment_id=experiment.experiment_id,
                        experiment_fk=experiment.id,
                    )
                    db.add(conditions)
                    db.flush()

                # Resolve compound
                comp = name_to_compound.get(comp_name.lower())
                if not comp:
                    errors.append(f"Row {idx+2}: compound '{comp_name}' not found; upload inventory first")
                    continue

                # Upsert additive
                existing_add = db.query(ChemicalAdditive).filter(
                    ChemicalAdditive.experiment_id == conditions.id,
                    ChemicalAdditive.compound_id == comp.id,
                ).first()

                # Parse order int
                try:
                    order_int = int(order_val) if order_val is not None and str(order_val).strip() != '' else None
                except Exception:
                    order_int = None

                method_text = str(method_val).strip() if method_val is not None and str(method_val).strip() != '' else None
                if method_text and len(method_text) > ADDITION_METHOD_MAX_LENGTH:
                    errors.append(
                        f"Row {idx+2}: method truncated to {ADDITION_METHOD_MAX_LENGTH} characters (was {len(method_text)})"
                    )
                    method_text = method_text[:ADDITION_METHOD_MAX_LENGTH]

                if existing_add:
                    existing_add.amount = amount_float
                    existing_add.unit = unit_enum
                    existing_add.addition_order = order_int
                    existing_add.addition_method = method_text
                    db.flush()
                    recalculate(existing_add, db)
                    updated += 1
                else:
                    new_add = ChemicalAdditive(
                        experiment_id=conditions.id,
                        compound_id=comp.id,
                        amount=amount_float,
                        unit=unit_enum,
                        addition_order=order_int,
                        addition_method=method_text,
                    )
                    db.add(new_add)
                    db.flush()
                    recalculate(new_add, db)
                    created += 1

                # Row body completed without exception or early `continue`.
                row_ok = True
            except Exception as e:
                errors.append(f"Row {idx+2}: {e}")
            finally:
                if row_ok:
                    savepoint.commit()
                else:
                    savepoint.rollback()

        return created, updated, skipped, errors


