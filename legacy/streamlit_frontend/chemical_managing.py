import streamlit as st
from typing import List, Optional, Dict, Any
import pandas as pd

from database import SessionLocal
from database.models import (
    ExperimentalConditions,
    ChemicalAdditive,
    Compound,
    AmountUnit,
)


def _resolve_conditions_id(
    db,
    conditions_id: Optional[int] = None,
    experiment_fk: Optional[int] = None,
    experiment_id: Optional[str] = None,
) -> Optional[int]:
    """
    Resolve and return the `ExperimentalConditions.id` for a given experiment context.
    Priority order: conditions_id -> experiment_fk -> experiment_id (string).
    Returns None if not found.
    """
    if conditions_id:
        cond = db.query(ExperimentalConditions).filter(ExperimentalConditions.id == conditions_id).first()
        return cond.id if cond else None

    if experiment_fk:
        cond = (
            db.query(ExperimentalConditions)
            .filter(ExperimentalConditions.experiment_fk == experiment_fk)
            .first()
        )
        return cond.id if cond else None

    if experiment_id:
        cond = (
            db.query(ExperimentalConditions)
            .filter(ExperimentalConditions.experiment_id == experiment_id)
            .first()
        )
        return cond.id if cond else None

    return None


def _get_amount_unit_options() -> List[str]:
    """Return a list of unit option strings from the AmountUnit enum."""
    return [u.value for u in AmountUnit]


def _list_current_additives(db, conditions_id: int) -> List[ChemicalAdditive]:
    return (
        db.query(ChemicalAdditive)
        .filter(ChemicalAdditive.experiment_id == conditions_id)
        .order_by(ChemicalAdditive.addition_order.asc().nulls_last(), ChemicalAdditive.id.asc())
        .all()
    )


def _list_compounds(db) -> List[Compound]:
    try:
        return db.query(Compound).order_by(Compound.name.asc()).all()
    except Exception as e:
        # Handle missing table gracefully
        if "no such table" in str(e).lower():
            st.info("Compound table not yet created. Add compounds in Chemical Management.")
            return []
        raise


def _upsert_additive(
    db,
    conditions_id: int,
    compound_id: int,
    amount: float,
    unit_value: str,
    addition_order: Optional[int] = None,
    addition_method: Optional[str] = None,
) -> ChemicalAdditive:
    """
    Insert or update a ChemicalAdditive for the given conditions and compound.
    Enforces uniqueness per (conditions_id, compound_id).
    """
    existing = (
        db.query(ChemicalAdditive)
        .filter(
            ChemicalAdditive.experiment_id == conditions_id,
            ChemicalAdditive.compound_id == compound_id,
        )
        .first()
    )

    unit_enum = None
    # Convert string to AmountUnit enum safely
    for u in AmountUnit:
        if u.value == unit_value:
            unit_enum = u
            break
    if unit_enum is None:
        raise ValueError(f"Invalid unit: {unit_value}")

    if existing:
        existing.amount = amount
        existing.unit = unit_enum
        existing.addition_order = addition_order
        existing.addition_method = addition_method.strip() if addition_method else None
        existing.calculate_derived_values()
        db.flush()
        return existing

    additive = ChemicalAdditive(
        experiment_id=conditions_id,
        compound_id=compound_id,
        amount=amount,
        unit=unit_enum,
        addition_order=addition_order,
        addition_method=addition_method.strip() if addition_method else None,
    )
    additive.calculate_derived_values()
    db.add(additive)
    db.flush()
    return additive


def _remove_additive(db, additive_id: int) -> None:
    obj = db.query(ChemicalAdditive).filter(ChemicalAdditive.id == additive_id).first()
    if obj:
        db.delete(obj)
        db.flush()


def _serialize_additives_to_rows(db, conditions_id: int) -> List[Dict[str, Any]]:
    """Return seed rows for editor from current additives for conditions_id."""
    # Build id->name mapping correctly; query full model or unpack tuples
    try:
        compounds = db.query(Compound).all()
        id_to_name = {c.id: c.name for c in compounds}
    except Exception:
        # Fallback in case of unusual session state; don't break template generation
        id_to_name = {}
    additives = _list_current_additives(db, conditions_id)
    return [
        {
            'compound': id_to_name.get(a.compound_id, ""),
            'amount': float(a.amount) if a.amount is not None else 0.0,
            'unit': a.unit.value if a.unit else _get_amount_unit_options()[0],
            'order': int(a.addition_order) if a.addition_order is not None else None,
            'method': a.addition_method or "",
        }
        for a in additives
    ]


def render_compound_manager(
    *,
    conditions_id: Optional[int] = None,
    experiment_fk: Optional[int] = None,
    experiment_id: Optional[str] = None,
    key_prefix: str = "cmp_mgr",
) -> List[Dict[str, Any]]:
    """
    Render a reusable UI component to manage compounds (ChemicalAdditives) for a single experiment.

    Args:
        conditions_id: `ExperimentalConditions.id` if already known.
        experiment_fk: `Experiment.id` (PK) to resolve conditions.
        experiment_id: `Experiment.experiment_id` (string) to resolve conditions.
        key_prefix: Unique prefix for Streamlit widget keys when used multiple times.

    Returns:
        A list of dictionaries describing current additives after any operations.
    """
    db = SessionLocal()
    try:
        resolved_conditions_id = _resolve_conditions_id(
            db,
            conditions_id=conditions_id,
            experiment_fk=experiment_fk,
            experiment_id=experiment_id,
        )

        st.markdown("#### Chemical Additives")

        if not resolved_conditions_id:
            st.info(
                "Experimental conditions not found yet. Save the experiment to create conditions, then manage compounds."
            )
            return []

        # Current additives
        existing_additives = _list_current_additives(db, resolved_conditions_id)

        if existing_additives:
            st.markdown("Current additives:")
            for additive in existing_additives:
                compound = db.query(Compound).filter(Compound.id == additive.compound_id).first()
                cols = st.columns([3, 2, 2, 2, 1])
                with cols[0]:
                    st.write(f"{compound.name if compound else 'Unknown'}")
                with cols[1]:
                    st.write(f"Amount: {additive.amount}")
                with cols[2]:
                    st.write(f"Unit: {additive.unit.value}")
                with cols[3]:
                    st.write(
                        f"Order: {additive.addition_order if additive.addition_order is not None else '-'}"
                    )
                with cols[4]:
                    if st.button(
                        "Remove",
                        key=f"{key_prefix}_rm_{additive.id}",
                    ):
                        try:
                            _remove_additive(db, additive.id)
                            db.commit()
                            st.success("Removed additive")
                            st.rerun()
                        except Exception as e:
                            db.rollback()
                            st.error(f"Failed to remove additive: {e}")

            st.markdown("---")
        else:
            st.info("No additives yet. Add your first compound below.")

        # Entry modes
        tab_table, tab_single = st.tabs(["Table editor", "Single entry"])

        # --- Single entry tab ---
        with tab_single:
            with st.form(key=f"{key_prefix}_form"):
                cols = st.columns([4, 2, 2, 2, 3])

                # Compound selection
                with cols[0]:
                    compounds = _list_compounds(db)
                    compound_options = [f"{c.name} ({c.formula})" if c.formula else c.name for c in compounds]
                    # Prefill from last template if available
                    last_template = st.session_state.get('last_additives_template')
                    prefill_row = last_template[0] if isinstance(last_template, list) and last_template else None
                    default_compound_idx = 0
                    if prefill_row and compounds:
                        try:
                            pre_name = prefill_row.get('compound')
                            names_only = [c.name for c in compounds]
                            if pre_name in names_only:
                                default_compound_idx = names_only.index(pre_name)
                        except Exception:
                            default_compound_idx = 0
                    selected_idx = st.selectbox(
                        "Compound",
                        options=list(range(len(compounds))),
                        format_func=lambda i: compound_options[i] if i is not None and i < len(compound_options) else "",
                        index=default_compound_idx if compounds else 0,
                        key=f"{key_prefix}_compound",
                    ) if compounds else None

                with cols[1]:
                    default_amount = 0.0
                    if prefill_row and isinstance(prefill_row.get('amount'), (int, float)):
                        try:
                            default_amount = float(prefill_row.get('amount'))
                        except Exception:
                            default_amount = 0.0
                    amount = st.number_input(
                        "Amount",
                        min_value=0.0,
                        step=0.0001,
                        format="%.4f",
                        value=default_amount,
                        key=f"{key_prefix}_amount",
                    )

                with cols[2]:
                    unit_options = _get_amount_unit_options()
                    default_unit_idx = 0
                    if prefill_row and prefill_row.get('unit') in unit_options:
                        default_unit_idx = unit_options.index(prefill_row.get('unit'))
                    unit = st.selectbox(
                        "Unit",
                        options=unit_options,
                        index=default_unit_idx,
                        key=f"{key_prefix}_unit",
                    )

                with cols[3]:
                    default_order = 0
                    if prefill_row:
                        try:
                            order_val = prefill_row.get('order')
                            default_order = int(order_val) if order_val is not None and str(order_val).strip() != '' else 0
                        except Exception:
                            default_order = 0
                    addition_order = st.number_input(
                        "Order (optional)",
                        min_value=0,
                        step=1,
                        format="%d",
                        value=default_order,
                        key=f"{key_prefix}_order",
                        help="Leave as 0 if no specific order is needed"
                    )

                with cols[4]:
                    default_method = prefill_row.get('method') if prefill_row else ""
                    addition_method = st.text_input(
                        "Method (optional)",
                        placeholder="solid / solution / dropwise ...",
                        value=default_method,
                        key=f"{key_prefix}_method",
                    )

                submitted = st.form_submit_button("Add / Update Additive")

            if submitted:
                if not compounds:
                    st.error("No compounds available. Add compounds in Chemical Management first.")
                else:
                    try:
                        selected_compound = compounds[selected_idx] if selected_idx is not None else None
                        if selected_compound is None:
                            st.error("Please select a compound.")
                        elif amount is None or amount <= 0:
                            st.error("Please enter a positive amount.")
                        else:
                            _upsert_additive(
                                db,
                                conditions_id=resolved_conditions_id,
                                compound_id=selected_compound.id,
                                amount=float(amount),
                                unit_value=unit,
                                addition_order=int(addition_order) if addition_order is not None else None,
                                addition_method=addition_method,
                            )
                            db.commit()
                            # Update last additives template in session for next experiment
                            try:
                                st.session_state['last_additives_template'] = _serialize_additives_to_rows(db, resolved_conditions_id)
                            except Exception:
                                pass
                            st.success("Additive saved")
                            st.rerun()
                    except Exception as e:
                        db.rollback()
                        st.error(f"Failed to save additive: {e}")

        # --- Bulk table editor tab ---
        with tab_table:
            compounds_all = _list_compounds(db)
            if not compounds_all:
                st.info("No compounds available. Add compounds in Chemical Management first.")
            else:
                compound_names = [c.name for c in compounds_all]
                name_to_id = {c.name: c.id for c in compounds_all}
                id_to_name = {c.id: c.name for c in compounds_all}

                # Seed table from existing additives, or from last template if none
                seed_rows = [
                    {
                        'compound': id_to_name.get(a.compound_id, ""),
                        'amount': float(a.amount) if a.amount is not None else 0.0,
                        'unit': a.unit.value if a.unit else _get_amount_unit_options()[0],
                        'order': int(a.addition_order) if a.addition_order is not None else None,
                        'method': a.addition_method or "",
                    }
                    for a in existing_additives
                ]
                if not seed_rows:
                    last_template = st.session_state.get('last_additives_template')
                    if isinstance(last_template, list) and last_template:
                        seed_rows = last_template

                # Persist editor data across reruns using session state
                editor_state_key = f"{key_prefix}_editor_df_{resolved_conditions_id}"
                if editor_state_key not in st.session_state:
                    st.session_state[editor_state_key] = pd.DataFrame(
                        seed_rows or [], columns=['compound', 'amount', 'unit', 'order', 'method']
                    )

                edited_df = st.data_editor(
                    st.session_state[editor_state_key],
                    num_rows="dynamic",
                    use_container_width=True,
                    key=f"{key_prefix}_editor_{resolved_conditions_id}",
                    column_config={
                        'compound': st.column_config.SelectboxColumn(
                            "Compound",
                            options=compound_names,
                            required=True,
                        ),
                        'amount': st.column_config.NumberColumn(
                            "Amount",
                            min_value=0.0,
                            step=0.0001,
                            format="%.4f",
                        ),
                        'unit': st.column_config.SelectboxColumn(
                            "Unit",
                            options=_get_amount_unit_options(),
                            required=True,
                        ),
                        'order': st.column_config.NumberColumn(
                            "Order (optional)",
                            min_value=0,
                            step=1,
                            format="%d",
                            required=False,
                        ),
                        'method': st.column_config.TextColumn(
                            "Method (optional)",
                        ),
                    },
                )

                # Update state with latest editor content
                if isinstance(edited_df, pd.DataFrame):
                    st.session_state[editor_state_key] = edited_df

                col_left, col_right = st.columns([1, 1])
                with col_left:
                    replace_all = st.checkbox(
                        "Replace existing additives with table",
                        key=f"{key_prefix}_replace_all",
                        value=False,
                    )
                with col_right:
                    apply_bulk = st.button("Apply table changes", key=f"{key_prefix}_apply")

                if apply_bulk:
                    try:
                        # Read from session state to avoid losing edits on rerun
                        df_current = st.session_state.get(editor_state_key)
                        rows = df_current.to_dict('records') if isinstance(df_current, pd.DataFrame) else []
                        # Optionally replace all
                        if replace_all:
                            for a in _list_current_additives(db, resolved_conditions_id):
                                _remove_additive(db, a.id)
                            db.flush()

                        # Upsert each valid row
                        for row in rows:
                            compound_name = (row.get('compound') or '').strip()
                            unit_val = (row.get('unit') or '').strip()
                            amount_val = row.get('amount')
                            if not compound_name or compound_name not in name_to_id:
                                continue
                            if not unit_val or unit_val not in _get_amount_unit_options():
                                continue
                            try:
                                amount_float = float(amount_val)
                            except (TypeError, ValueError):
                                continue
                            if amount_float <= 0:
                                continue

                            ord_val = row.get('order')
                            try:
                                ord_int = int(ord_val) if ord_val is not None and str(ord_val).strip() != '' else None
                            except (TypeError, ValueError):
                                ord_int = None

                            method_val = (row.get('method') or '').strip() or None

                            _upsert_additive(
                                db,
                                conditions_id=resolved_conditions_id,
                                compound_id=name_to_id[compound_name],
                                amount=amount_float,
                                unit_value=unit_val,
                                addition_order=ord_int,
                                addition_method=method_val,
                            )

                        db.commit()
                        # Persist this set as the last template for next experiment in session
                        try:
                            st.session_state['last_additives_template'] = [
                                {
                                    'compound': (row.get('compound') or '').strip(),
                                    'amount': float(row.get('amount') or 0.0),
                                    'unit': (row.get('unit') or '').strip() or _get_amount_unit_options()[0],
                                    'order': int(row.get('order')) if row.get('order') is not None and str(row.get('order')).strip() != '' else None,
                                    'method': (row.get('method') or '').strip(),
                                }
                                for row in rows
                                if (row.get('compound') or '').strip()
                            ]
                        except Exception:
                            pass
                        st.success("Bulk changes applied")
                        st.rerun()
                    except Exception as e:
                        db.rollback()
                        st.error(f"Failed to apply bulk changes: {e}")

        # Return current state
        updated = _list_current_additives(db, resolved_conditions_id)
        return [
            {
                'id': a.id,
                'compound_id': a.compound_id,
                'amount': a.amount,
                'unit': a.unit.value,
                'addition_order': a.addition_order,
                'addition_method': a.addition_method,
            }
            for a in updated
        ]
    finally:
        db.close()


__all__ = [
    'render_compound_manager',
]

