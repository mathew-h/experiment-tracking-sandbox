from __future__ import annotations
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from database.models.experiments import Experiment
from database.models.conditions import ExperimentalConditions
from database.models.results import ExperimentalResults, ScalarResults, ICPResults
from database.models.enums import ExperimentStatus
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.dashboard import (
    ReactorStatusResponse, ExperimentTimelineResponse, TimelinePoint,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/reactor-status", response_model=list[ReactorStatusResponse])
def get_reactor_status(
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ReactorStatusResponse]:
    """Single query: all reactors with their current ONGOING experiment. No N+1."""
    rows = db.execute(
        select(
            ExperimentalConditions.reactor_number,
            Experiment.id,
            Experiment.experiment_id,
            Experiment.status,
            Experiment.created_at,
            ExperimentalConditions.temperature_c,
            ExperimentalConditions.experiment_type,
        )
        .join(Experiment, Experiment.id == ExperimentalConditions.experiment_fk)
        .where(Experiment.status == ExperimentStatus.ONGOING)
        .where(ExperimentalConditions.reactor_number.isnot(None))
        .order_by(ExperimentalConditions.reactor_number, Experiment.created_at.desc())
    ).all()

    # Deduplicate: keep first (most-recent) per reactor_number
    seen: set[int] = set()
    result: list[ReactorStatusResponse] = []
    for row in rows:
        rn = row.reactor_number
        if rn in seen:
            continue
        seen.add(rn)
        result.append(ReactorStatusResponse(
            reactor_number=rn,
            experiment_id=row.experiment_id,
            status=row.status,
            experiment_db_id=row.id,
            started_at=row.created_at,
            temperature_c=row.temperature_c,
            experiment_type=row.experiment_type,
        ))
    return result


@router.get("/timeline/{experiment_id}", response_model=ExperimentTimelineResponse)
def get_experiment_timeline(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentTimelineResponse:
    """Return all result timepoints for an experiment with data-presence flags."""
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

    # Check scalar/ICP presence in bulk (avoid N+1)
    result_ids = [r.id for r in results]
    scalar_ids = set(
        db.execute(select(ScalarResults.result_id).where(ScalarResults.result_id.in_(result_ids)))
        .scalars().all()
    )
    icp_ids = set(
        db.execute(select(ICPResults.result_id).where(ICPResults.result_id.in_(result_ids)))
        .scalars().all()
    )

    timepoints = [
        TimelinePoint(
            result_id=r.id,
            time_post_reaction_days=r.time_post_reaction_days,
            time_post_reaction_bucket_days=r.time_post_reaction_bucket_days,
            is_primary=r.is_primary_timepoint_result,
            has_scalar=r.id in scalar_ids,
            has_icp=r.id in icp_ids,
        )
        for r in results
    ]

    return ExperimentTimelineResponse(
        experiment_id=experiment_id,
        status=exp.status,
        timepoints=timepoints,
    )
