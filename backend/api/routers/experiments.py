from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.enums import ExperimentStatus
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.experiments import (
    ExperimentCreate, ExperimentUpdate, ExperimentListItem, ExperimentListResponse,
    ExperimentResponse, ExperimentDetailResponse, ExperimentStatusUpdate, NextIdResponse,
    NoteCreate, NoteResponse, NoteUpdate,
)
from backend.api.schemas.results import (
    ResultWithFlagsResponse, BackgroundAmmoniumUpdate, BackgroundAmmoniumUpdated,
)
from database.models.results import ExperimentalResults, ScalarResults
from database.models.chemicals import Compound, ChemicalAdditive
from database.models.conditions import ExperimentalConditions
from backend.api.schemas.chemicals import AdditiveResponse, ChemicalAdditiveUpsert
from backend.services.calculations.registry import recalculate

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/experiments", tags=["experiments"])

# Prefix mapping for next-id endpoint
_TYPE_PREFIX: dict[str, str] = {
    "HPHT": "HPHT",
    "Serum": "SERUM",
    "Autoclave": "AUTOCLAVE",
    "Core Flood": "CF",
}


@router.get("", response_model=ExperimentListResponse)
def list_experiments(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    status: ExperimentStatus | None = None,
    researcher: str | None = None,
    search: str | None = None,
    sample_id: str | None = None,
    experiment_type: str | None = None,
    reactor_number: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentListResponse:
    """List experiments with optional filters, joins for conditions/additives, and pagination."""
    from database.models.conditions import ExperimentalConditions

    stmt = select(Experiment).order_by(Experiment.experiment_number.desc())
    if status:
        stmt = stmt.where(Experiment.status == status)
    if researcher:
        stmt = stmt.where(Experiment.researcher == researcher)
    if search:
        stmt = stmt.where(Experiment.experiment_id.ilike(f"%{search}%"))
    if sample_id:
        stmt = stmt.where(Experiment.sample_id.ilike(f"%{sample_id}%"))
    if date_from:
        stmt = stmt.where(Experiment.date >= date_from)
    if date_to:
        stmt = stmt.where(Experiment.date <= date_to)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.offset(skip).limit(limit)).scalars().all()

    items = []
    for exp in rows:
        item_data = {c.key: getattr(exp, c.key) for c in Experiment.__table__.columns}
        # Join conditions for experiment_type and reactor_number
        cond = db.execute(
            select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
        ).scalar_one_or_none()
        item_data["experiment_type"] = cond.experiment_type if cond else None
        item_data["reactor_number"] = cond.reactor_number if cond else None
        # In-memory filter for type/reactor (acceptable for < 500 experiments)
        # TODO: replace with proper JOIN query when lab data grows
        if experiment_type and item_data["experiment_type"] != experiment_type:
            total -= 1
            continue
        if reactor_number is not None and item_data["reactor_number"] != reactor_number:
            total -= 1
            continue
        # Additives summary — inline query avoids view dependency
        additive_row = db.execute(
            text("""
                SELECT string_agg(c.name || ' ' || CAST(a.amount AS TEXT) || ' ' || a.unit, '; ')
                FROM chemical_additives a
                JOIN experimental_conditions ec ON ec.id = a.experiment_id
                JOIN compounds c ON c.id = a.compound_id
                WHERE ec.experiment_fk = :exp_fk
            """),
            {"exp_fk": exp.id},
        ).fetchone()
        item_data["additives_summary"] = additive_row[0] if additive_row else None
        # First note as condition note
        first_note = db.execute(
            select(ExperimentNotes)
            .where(ExperimentNotes.experiment_fk == exp.id)
            .order_by(ExperimentNotes.id.asc())
            .limit(1)
        ).scalar_one_or_none()
        item_data["condition_note"] = first_note.note_text if first_note else None
        items.append(ExperimentListItem.model_validate(item_data))

    return ExperimentListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/next-id", response_model=NextIdResponse)
def get_next_experiment_id(
    type: str = Query(..., description="Experiment type"),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> NextIdResponse:
    """Return the next auto-incremented experiment ID for the given type."""
    prefix = _TYPE_PREFIX.get(type, type.upper().replace(" ", "_"))
    pattern = f"{prefix}_%"
    rows = db.execute(
        select(Experiment.experiment_id).where(Experiment.experiment_id.like(pattern))
    ).scalars().all()
    max_num = 0
    for eid in rows:
        suffix = eid[len(prefix) + 1:]
        if suffix.isdigit():
            max_num = max(max_num, int(suffix))
    next_num = str(max_num + 1).zfill(3)
    return NextIdResponse(next_id=f"{prefix}_{next_num}")


@router.get("/next-ids")
def get_next_experiment_ids(
    db: Session = Depends(get_db),
) -> dict:
    """
    Return the next sequence number for each experiment type, derived by
    parsing the numeric suffix from experiment_id (same logic as /next-id).
    No auth required — read-only, non-sensitive.

    Response: ``{"HPHT": 107, "Serum": 165, "CF": 15, "Autoclave": 8}``
    """
    label_prefix = {"HPHT": "HPHT", "Serum": "SERUM", "CF": "CF", "Autoclave": "Autoclave"}
    result: dict[str, int] = {}
    for label, prefix in label_prefix.items():
        rows = db.execute(
            select(Experiment.experiment_id)
            .where(Experiment.experiment_id.like(f"{prefix}_%"))
        ).scalars().all()
        max_num = 0
        for eid in rows:
            suffix = eid[len(prefix) + 1:]
            if suffix.isdigit():
                max_num = max(max_num, int(suffix))
        result[label] = max_num + 1
    return result


@router.get("/{experiment_id}/results", response_model=list[ResultWithFlagsResponse])
def get_experiment_results(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ResultWithFlagsResponse]:
    """Return all result timepoints for an experiment, with scalar and ICP existence flags."""
    from database.models.results import ExperimentalResults, ScalarResults, ICPResults

    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    results = db.execute(
        select(ExperimentalResults)
        .where(ExperimentalResults.experiment_fk == exp.id)
        .order_by(ExperimentalResults.time_post_reaction_days)
    ).scalars().all()

    out = []
    for r in results:
        scalar = db.execute(
            select(ScalarResults).where(ScalarResults.result_id == r.id)
        ).scalar_one_or_none()
        icp = db.execute(
            select(ICPResults).where(ICPResults.result_id == r.id)
        ).scalar_one_or_none()
        out.append(ResultWithFlagsResponse(
            id=r.id,
            experiment_fk=r.experiment_fk,
            time_post_reaction_days=r.time_post_reaction_days,
            time_post_reaction_bucket_days=r.time_post_reaction_bucket_days,
            cumulative_time_post_reaction_days=r.cumulative_time_post_reaction_days,
            is_primary_timepoint_result=r.is_primary_timepoint_result,
            description=r.description,
            created_at=r.created_at,
            has_scalar=scalar is not None,
            has_icp=icp is not None,
            has_brine_modification=r.has_brine_modification,
            brine_modification_description=r.brine_modification_description,
            grams_per_ton_yield=scalar.grams_per_ton_yield if scalar else None,
            h2_grams_per_ton_yield=scalar.h2_grams_per_ton_yield if scalar else None,
            h2_micromoles=scalar.h2_micromoles if scalar else None,
            gross_ammonium_concentration_mM=scalar.gross_ammonium_concentration_mM if scalar else None,
            final_conductivity_mS_cm=scalar.final_conductivity_mS_cm if scalar else None,
            final_ph=scalar.final_ph if scalar else None,
            scalar_measurement_date=scalar.measurement_date if scalar else None,
        ))
    return out


@router.patch("/{experiment_id}/status", response_model=ExperimentResponse)
def update_experiment_status(
    experiment_id: str,
    payload: ExperimentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentResponse:
    """Inline status update without full patch."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    exp.status = payload.status
    db.commit()
    db.refresh(exp)
    return ExperimentResponse.model_validate(exp)


@router.get("/{experiment_id}/additives", response_model=list[AdditiveResponse])
def list_experiment_additives(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[AdditiveResponse]:
    """List chemical additives for an experiment by its string ID. Returns [] if no conditions exist."""
    conditions = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if conditions is None:
        return []
    rows = db.execute(
        select(ChemicalAdditive)
        .where(ChemicalAdditive.experiment_id == conditions.id)
        .order_by(ChemicalAdditive.addition_order)
    ).scalars().all()
    return [AdditiveResponse.model_validate(r) for r in rows]


@router.put("/{experiment_id}/additives/{compound_id}", response_model=AdditiveResponse)
def upsert_experiment_additive(
    experiment_id: str,
    compound_id: int,
    payload: ChemicalAdditiveUpsert,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> AdditiveResponse:
    """Upsert a chemical additive for an experiment — create if new, update if exists.

    Accepts experiment string ID and resolves conditions row internally.
    ChemicalAdditive.experiment_id is a FK to experimental_conditions.id (not experiments.id).
    """
    conditions = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if conditions is None:
        raise HTTPException(status_code=404, detail="Experiment conditions not found")
    compound = db.get(Compound, compound_id)
    if compound is None:
        raise HTTPException(status_code=404, detail="Compound not found")
    existing = db.execute(
        select(ChemicalAdditive)
        .where(ChemicalAdditive.experiment_id == conditions.id)
        .where(ChemicalAdditive.compound_id == compound_id)
    ).scalar_one_or_none()
    if existing:
        old_vals = {"amount": existing.amount, "unit": existing.unit.value if existing.unit else None}
        mod_type = "update"
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(existing, k, v)
        additive = existing
    else:
        old_vals = None
        mod_type = "create"
        additive = ChemicalAdditive(
            experiment_id=conditions.id,
            compound_id=compound_id,
            **payload.model_dump(),
        )
        db.add(additive)
    db.flush()
    recalculate(additive, db)
    exp = db.execute(select(Experiment).where(Experiment.experiment_id == experiment_id)).scalar_one_or_none()
    new_vals = {"amount": additive.amount, "unit": additive.unit.value if additive.unit else None}
    if exp is not None:
        db.add(ModificationsLog(
            experiment_id=experiment_id,
            experiment_fk=exp.id,
            modified_by=current_user.uid,
            modification_type=mod_type,
            modified_table="chemical_additives",
            old_values=old_vals,
            new_values=new_vals,
        ))
    db.commit()
    db.refresh(additive)
    log.info("additive_upserted", experiment_id=experiment_id, compound_id=compound_id)
    return AdditiveResponse.model_validate(additive)


@router.delete("/{experiment_id}/additives/{compound_id}", status_code=204)
def delete_experiment_additive(
    experiment_id: str,
    compound_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> Response:
    """Remove a chemical additive from an experiment."""
    conditions = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if conditions is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    additive = db.execute(
        select(ChemicalAdditive)
        .where(ChemicalAdditive.experiment_id == conditions.id)
        .where(ChemicalAdditive.compound_id == compound_id)
    ).scalar_one_or_none()
    if additive is None:
        raise HTTPException(status_code=404, detail="Additive not found")
    exp = db.execute(select(Experiment).where(Experiment.experiment_id == experiment_id)).scalar_one_or_none()
    compound = db.get(Compound, compound_id)
    old_vals = {
        "compound_id": compound_id,
        "compound_name": compound.name if compound else None,
        "amount": additive.amount,
        "unit": additive.unit.value if additive.unit else None,
    }
    db.delete(additive)
    if exp is not None:
        db.add(ModificationsLog(
            experiment_id=experiment_id,
            experiment_fk=exp.id,
            modified_by=current_user.uid,
            modification_type="delete",
            modified_table="chemical_additives",
            old_values=old_vals,
            new_values=None,
        ))
    db.commit()
    log.info("additive_deleted", experiment_id=experiment_id, compound_id=compound_id)
    return Response(status_code=204)


@router.patch("/{experiment_id}/background-ammonium", response_model=BackgroundAmmoniumUpdated)
def set_experiment_background_ammonium(
    experiment_id: str,
    payload: BackgroundAmmoniumUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> BackgroundAmmoniumUpdated:
    """Apply a single background ammonium value to every scalar result for an experiment.

    Updates background_ammonium_concentration_mM on all ScalarResults rows for the
    experiment and triggers recalculation of derived yield fields on each row.
    """
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    result_ids = db.execute(
        select(ExperimentalResults.id).where(ExperimentalResults.experiment_fk == exp.id)
    ).scalars().all()

    scalars = db.execute(
        select(ScalarResults).where(ScalarResults.result_id.in_(result_ids))
    ).scalars().all()

    for scalar in scalars:
        scalar.background_ammonium_concentration_mM = payload.value
        db.flush()
        recalculate(scalar, db)

    db.commit()
    log.info(
        "background_ammonium_updated",
        experiment_id=experiment_id,
        value=payload.value,
        count=len(scalars),
    )
    return BackgroundAmmoniumUpdated(updated=len(scalars))


@router.get("/{experiment_id}/exists")
def check_experiment_id_exists(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> dict:
    """Return whether an experiment_id string is already in use."""
    exists = db.execute(
        select(Experiment.id).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    return {"exists": exists is not None}


@router.get("/{experiment_id}", response_model=ExperimentDetailResponse)
def get_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentDetailResponse:
    """Get a single experiment with nested conditions, notes, and modifications."""
    from database.models.conditions import ExperimentalConditions
    from database.models.experiments import ModificationsLog
    from backend.api.schemas.conditions import ConditionsResponse

    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    cond = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
    ).scalar_one_or_none()
    notes = db.execute(
        select(ExperimentNotes)
        .where(ExperimentNotes.experiment_fk == exp.id)
        .order_by(ExperimentNotes.id.asc())
    ).scalars().all()
    mods = db.execute(
        select(ModificationsLog)
        .where(ModificationsLog.experiment_fk == exp.id)
        .order_by(ModificationsLog.created_at.desc())
    ).scalars().all()

    cond_dict = ConditionsResponse.model_validate(cond).model_dump() if cond else None
    notes_list = [
        {"id": n.id, "note_text": n.note_text, "created_at": n.created_at.isoformat()}
        for n in notes
    ]
    mods_list = [
        {
            "id": m.id,
            "modified_by": m.modified_by,
            "modification_type": m.modification_type,
            "modified_table": m.modified_table,
            "old_values": m.old_values,
            "new_values": m.new_values,
            "created_at": m.created_at.isoformat(),
        }
        for m in mods
    ]
    base = ExperimentResponse.model_validate(exp)
    return ExperimentDetailResponse(**base.model_dump(), conditions=cond_dict, notes=notes_list, modifications=mods_list)


@router.post("", response_model=ExperimentResponse, status_code=201)
def create_experiment(
    payload: ExperimentCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentResponse:
    """Create a new experiment."""
    data = payload.model_dump()
    if data.get("experiment_number") is None:
        max_num = db.execute(select(func.max(Experiment.experiment_number))).scalar() or 0
        data["experiment_number"] = max_num + 1
    exp = Experiment(**data)
    db.add(exp)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Experiment ID already exists")
    db.refresh(exp)
    log.info("experiment_created", experiment_id=exp.experiment_id, user=current_user.email)
    return ExperimentResponse.model_validate(exp)


@router.patch("/{experiment_id}", response_model=ExperimentResponse)
def update_experiment(
    experiment_id: str,
    payload: ExperimentUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentResponse:
    """Update mutable fields on an experiment. If experiment_id is provided and differs
    from the path param, treats it as a rename: checks uniqueness, updates
    ExperimentalConditions.experiment_id, and writes a ModificationsLog entry."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    data = payload.model_dump(exclude_unset=True)
    new_id = data.pop("experiment_id", None)

    for field, value in data.items():
        setattr(exp, field, value)

    if new_id is not None:
        new_id = new_id.strip()
        if not new_id:
            raise HTTPException(status_code=422, detail="experiment_id cannot be blank")
        if new_id != experiment_id:
            conflict = db.execute(
                select(Experiment.id).where(Experiment.experiment_id == new_id)
            ).scalar_one_or_none()
            if conflict is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Experiment ID '{new_id}' already exists",
                )
            exp.experiment_id = new_id
            # Keep denormalized string in conditions in sync so additives endpoints work
            cond = db.execute(
                select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
            ).scalar_one_or_none()
            if cond is not None:
                cond.experiment_id = new_id
            db.add(ModificationsLog(
                experiment_id=new_id,
                experiment_fk=exp.id,
                modified_by=current_user.uid,
                modification_type="update",
                modified_table="experiments",
                old_values={"experiment_id": experiment_id},
                new_values={"experiment_id": new_id},
            ))
            log.info("experiment_renamed", old_id=experiment_id, new_id=new_id, user=current_user.uid)

    db.commit()
    db.refresh(exp)
    return ExperimentResponse.model_validate(exp)


@router.delete("/{experiment_id}", status_code=204)
def delete_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> Response:
    """Delete an experiment and all cascaded records."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    db.delete(exp)
    db.commit()
    log.info("experiment_deleted", experiment_id=experiment_id, user=current_user.email)
    return Response(status_code=204)


@router.post("/{experiment_id}/notes", response_model=NoteResponse, status_code=201)
def add_note(
    experiment_id: str,
    payload: NoteCreate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> NoteResponse:
    """Append a timestamped note to an experiment. 404 if the experiment does not exist."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    note = ExperimentNotes(
        experiment_id=experiment_id,
        experiment_fk=exp.id,
        note_text=payload.note_text,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return NoteResponse.model_validate(note)


@router.patch("/{experiment_id}/notes/{note_id}", response_model=NoteResponse)
def patch_note(
    experiment_id: str,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> NoteResponse:
    """Edit the text of an existing note. No-op if text is unchanged. Writes ModificationsLog."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    note = db.execute(
        select(ExperimentNotes)
        .where(ExperimentNotes.id == note_id)
        .where(ExperimentNotes.experiment_fk == exp.id)
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.note_text == payload.note_text:
        return NoteResponse.model_validate(note)
    old_text = note.note_text
    note.note_text = payload.note_text
    db.flush()
    db.add(ModificationsLog(
        experiment_id=experiment_id,
        experiment_fk=exp.id,
        modified_by=current_user.email,
        modification_type="update",
        modified_table="experiment_notes",
        old_values={"note_text": old_text},
        new_values={"note_text": payload.note_text},
    ))
    db.commit()
    db.refresh(note)
    log.info("note_updated", experiment_id=experiment_id, note_id=note_id)
    return NoteResponse.model_validate(note)
