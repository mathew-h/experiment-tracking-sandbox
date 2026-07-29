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
                # Design note: this is a non-fatal, row-scoped notice, but it is routed into
                # `errors` (not a separate `warnings` list) per this file's original spec. The
                # only current caller -- legacy/streamlit_frontend/bulk_uploads.py, which treats
                # ANY non-empty `errors` as a full-batch rollback -- will therefore discard an
                # otherwise-successful upload over a mere truncation notice. Today's blast radius
                # is zero (that caller is retired Streamlit; this service has no FastAPI route).
                # A future live caller of this service should treat `errors` non-fatally per-row
                # (mirroring how new_experiments.py's API layer already treats its separate
                # `warnings` list) rather than blanket-failing the batch on any entry.
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
                # savepoint.commit() (RELEASE SAVEPOINT) flushes the session first, so a dirty
                # instance left over by recalculate() can still fail here even though row_ok is
                # True. If that commit itself raises, it must not escape this `finally` uncaught
                # (issue #96 review finding) -- an uncaught raise here would unwind the whole
                # upload past this row's own isolation, reproducing the original all-or-nothing
                # failure mode from a different trigger point. Roll back and record a row-scoped
                # error instead, exactly like an in-body failure.
                if row_ok:
                    try:
                        savepoint.commit()
                    except Exception as commit_error:
                        savepoint.rollback()
                        errors.append(f"Row {idx+2}: {commit_error}")
                else:
                    savepoint.rollback()

        return created, updated, skipped, errors


