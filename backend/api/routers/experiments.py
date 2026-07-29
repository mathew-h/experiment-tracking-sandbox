from __future__ import annotations
from datetime import date
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func, text, update, case, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.enums import ExperimentStatus
from database.experiment_id_parser import split_timepoint_token
from backend.services.replicate_collapse import collapse_by_stem, timepoint_stem_expr
from backend.api.dependencies.db import get_db
from backend.auth.firebase_auth import verify_firebase_token, FirebaseUser
from backend.api.schemas.experiments import (
    ExperimentCreate, ExperimentUpdate, ExperimentListItem, ExperimentListResponse,
    ExperimentResponse, ExperimentDetailResponse, ExperimentStatusUpdate, NextIdResponse,
    NoteCreate, NoteResponse, NoteUpdate, ReplicateGroupMember, ReplicateGroupResponse,
    ReplicateGroupMemberDetail, ReplicateGroupDetailResponse,
    ReplicateCreateRequest, ReplicateCreateResponse,
)
from backend.services.replicate_groups import (
    GroupData, group_exists, resolve_group, resolve_rollup_rows,
)
from backend.api.schemas.results import (
    ResultWithFlagsResponse, BackgroundAmmoniumUpdate, BackgroundAmmoniumUpdated,
    RollupTimepointResponse,
)
from database.models.results import ExperimentalResults, ScalarResults
from database.models.chemicals import Compound, ChemicalAdditive
from database.models.conditions import ExperimentalConditions
from database.models.analysis import ExternalAnalysis
from database.models.xrd import XRDPhase
from database.models.notion_sync import ReactorChangeRequest
from database.models.samples import SampleInfo
from backend.api.schemas.notion_sync import (
    ChangeRequestResponse, ChangeRequestUpsertRequest, RecentChangeRequestsResponse,
)
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


def _is_group_parent_spelling(derivation, treatment, replicate_label) -> bool:
    """True when a parsed experiment_id (derivation_number, treatment_variant,
    replicate_label from parse_experiment_id) names a replicate GROUP PARENT
    spelling: bare stem, or explicit -0/-1 (see database/lineage_utils.py::
    update_experiment_lineage). False for lettered members (e.g. SERUM_040a)
    and for sequential re-runs (e.g. SERUM_040-2), which are never parents.
    """
    return treatment is None and replicate_label is None and (derivation is None or derivation in (0, 1))


def _build_list_item(db: Session, exp: Experiment) -> dict:
    """Build the ExperimentListItem payload dict for one experiment row."""
    item_data = {c.key: getattr(exp, c.key) for c in Experiment.__table__.columns}
    cond = db.execute(
        select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
    ).scalar_one_or_none()
    item_data["experiment_type"] = cond.experiment_type if cond else None
    item_data["reactor_number"] = cond.reactor_number if cond else None
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
    first_note = db.execute(
        select(ExperimentNotes)
        .where(ExperimentNotes.experiment_fk == exp.id)
        .order_by(ExperimentNotes.id.asc())
        .limit(1)
    ).scalar_one_or_none()
    item_data["condition_note"] = first_note.note_text if first_note else None
    return item_data


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
    description: str | None = None,
    group_replicates: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ExperimentListResponse:
    """List experiments with optional filters, joins for conditions/additives, and pagination."""
    # First note per experiment (the "description" shown in the Description column) —
    # same pattern as backend/api/routers/dashboard.py.
    first_note_sq = (
        select(ExperimentNotes.experiment_fk, func.min(ExperimentNotes.id).label("min_note_id"))
        .group_by(ExperimentNotes.experiment_fk)
        .subquery()
    )
    note_sq = (
        select(ExperimentNotes.experiment_fk, ExperimentNotes.note_text)
        .join(first_note_sq, ExperimentNotes.id == first_note_sq.c.min_note_id)
        .subquery()
    )

    # Outer-join conditions/first-note so type, reactor #, and description filters run in
    # SQL before pagination — filtering these in Python after offset/limit produced wrong
    # totals and could return an empty page 1 even when matches existed (#64). Both joins
    # are at most 1 row per experiment (ExperimentalConditions is 1:1; note_sq is keyed by
    # min note id), so this cannot fan out rows or inflate `total`.
    stmt = (
        select(Experiment)
        .outerjoin(ExperimentalConditions, ExperimentalConditions.experiment_fk == Experiment.id)
        .outerjoin(note_sq, note_sq.c.experiment_fk == Experiment.id)
        .order_by(Experiment.experiment_number.desc())
    )
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
    if experiment_type:
        stmt = stmt.where(ExperimentalConditions.experiment_type == experiment_type)
    if reactor_number is not None:
        stmt = stmt.where(ExperimentalConditions.reactor_number == reactor_number)
    if description:
        stmt = stmt.where(note_sq.c.note_text.ilike(f"%{description}%"))

    if group_replicates:
        # Grouped mode: paginate over "top-level rows" (buckets). Bucket key
        # (#87 D2): a lettered member (replicate_label IS NOT NULL) buckets on
        # COALESCE(base_experiment_id, experiment_id) -- a STRING, since the
        # group parent frequently does not exist as a row (orphan sets are the
        # common case, not the edge case). A BARE-STEM parent (base_experiment_id
        # == its own experiment_id, no letter, no treatment) buckets on its own
        # experiment_id, which already equals its lettered members' key, so it
        # joins their group naturally. An explicit "-0"/"-1" parent spelling
        # (e.g. HPHT_012-0) is different: its own experiment_id is NOT the
        # stem, so it needs an explicit branch bucketing it on base_experiment_id
        # (the stem) to join its lettered members. Everything else -- standalone
        # experiments and non-lettered derivations like sequential re-runs
        # (SERUM_001-2) or treatments (SERUM_001_Desorption) -- buckets on its
        # OWN experiment_id and so always stands alone.
        #
        # Because base_experiment_id may not name an existing row, the
        # representative for a bucket can't always be resolved from a single
        # matched row (e.g. filtering to just "b" of an orphan a/b/c set must
        # still resolve representative "a", which didn't match the filter).
        # So: first find which bucket keys are touched by matched rows, then
        # resolve full bucket membership from the UNFILTERED table and rank
        # each bucket's rows to pick one representative: the parent/bare-stem
        # row if one exists (rank 0), otherwise the lowest-ordered lettered
        # member (replicate_label ASC, id_timepoint_days ASC NULLS FIRST,
        # experiment_number ASC).
        def _bucket_key_expr(col):
            return case(
                (
                    col.replicate_label.isnot(None),
                    func.coalesce(col.base_experiment_id, col.experiment_id),
                ),
                (
                    or_(
                        col.experiment_id == col.base_experiment_id.concat("-0"),
                        col.experiment_id == col.base_experiment_id.concat("-1"),
                    ),
                    col.base_experiment_id,
                ),
                # Issue #98: strip a trailing '-t<days>' token here. Without
                # this, a letterless timepoint vial (SERUM_001-t7) buckets on
                # its own raw ID and renders as a SECOND top-level row carrying
                # the same displayed label as the real SERUM_001 row. A no-op
                # for every ID without the token, so no existing bucket moves.
                else_=timepoint_stem_expr(col),
            )

        matched_sq = stmt.subquery()
        matched_bucket_key = _bucket_key_expr(matched_sq.c)
        matched_keys_sq = select(matched_bucket_key.label("bucket_key")).distinct().subquery()

        full_bucket_key = _bucket_key_expr(Experiment)
        is_parent_like = case((Experiment.replicate_label.is_(None), 0), else_=1)
        ranked_sq = (
            select(
                Experiment.id.label("id"),
                func.row_number().over(
                    partition_by=full_bucket_key,
                    order_by=(
                        is_parent_like,
                        # D7 / gap 8: a flagged vial must never represent the
                        # group while a clean sibling exists -- the
                        # representative supplies the row's Sample, Reactor,
                        # Date, Description and Additives columns.
                        Experiment.is_outlier.asc(),
                        Experiment.replicate_label.asc(),
                        Experiment.id_timepoint_days.asc().nulls_first(),
                        Experiment.experiment_number.asc(),
                    ),
                ).label("rn"),
            )
            .where(full_bucket_key.in_(select(matched_keys_sq.c.bucket_key)))
            .subquery()
        )
        reps_sq = select(ranked_sq.c.id).where(ranked_sq.c.rn == 1).subquery()

        total = db.execute(select(func.count()).select_from(reps_sq)).scalar_one()
        page_stmt = (
            select(Experiment)
            .where(Experiment.id.in_(select(reps_sq.c.id)))
            .order_by(Experiment.experiment_number.desc())
        )
        rows = db.execute(page_stmt.offset(skip).limit(limit)).scalars().all()
    else:
        # Flat mode: collapse rows that differ ONLY by the trailing '-t<days>'
        # token (issue #98 D1). SERUM_001a-t1 / SERUM_001a-t3 are one replicate
        # sampled twice, so they render as ONE row labeled SERUM_001a.
        #
        # Unlike the grouped branch above -- which resolves bucket membership
        # from the UNFILTERED table so that filtering to "b" still resolves
        # representative "a" -- this collapses only rows that PASSED the
        # filters. A filter therefore never produces a row claiming vials it
        # excluded, and vial_count always describes visible data.
        matched_sq = stmt.subquery()
        stem = timepoint_stem_expr(matched_sq.c)
        ranked_sq = select(
            matched_sq.c.id.label("id"),
            stem.label("stem"),
            func.row_number().over(
                partition_by=stem,
                order_by=(
                    matched_sq.c.is_outlier.asc(),
                    matched_sq.c.id_timepoint_days.asc().nulls_first(),
                    matched_sq.c.experiment_number.asc(),
                ),
            ).label("rn"),
            func.count().over(partition_by=stem).label("vial_count"),
        ).subquery()
        reps_sq = (
            select(ranked_sq.c.id, ranked_sq.c.stem, ranked_sq.c.vial_count)
            .where(ranked_sq.c.rn == 1)
            .subquery()
        )
        total = db.execute(select(func.count()).select_from(reps_sq)).scalar_one()
        rep_rows = db.execute(
            select(Experiment, reps_sq.c.stem, reps_sq.c.vial_count)
            .join(reps_sq, reps_sq.c.id == Experiment.id)
            .order_by(Experiment.experiment_number.desc())
            .offset(skip)
            .limit(limit)
        ).all()
        rows = [row[0] for row in rep_rows]
        flat_collapse = {row[0].id: (row[1], row[2]) for row in rep_rows}

    items = []
    for exp in rows:
        item_data = _build_list_item(db, exp)
        if not group_replicates:
            # Issue #98: label the row by its timepoint stem so the internal
            # '-t<days>' token never reaches the UI.
            stem, vial_count = flat_collapse[exp.id]
            item_data["group_display_id"] = stem
            item_data["vial_count"] = vial_count
        if group_replicates:
            # Bucket key for this representative -- mirrors Block A: a
            # lettered representative (orphan-set case) buckets on its own
            # base_experiment_id; an explicit "-0"/"-1" parent spelling also
            # buckets on base_experiment_id (the stem) to join its lettered
            # members; a bare-stem/standalone representative buckets on its
            # own experiment_id. Members are fetched from the UNFILTERED
            # table (attached in full regardless of whether they matched the
            # query filters) and identified by id, never by replicate_label
            # (a '-t<days>' vial shares its letter with its parent vial).
            if exp.replicate_label is not None:
                bucket_key = exp.base_experiment_id or exp.experiment_id
            elif exp.base_experiment_id and exp.experiment_id in (
                f"{exp.base_experiment_id}-0", f"{exp.base_experiment_id}-1",
            ):
                bucket_key = exp.base_experiment_id
            else:
                bucket_key = exp.experiment_id
            # Every row in this bucket, resolved from the UNFILTERED table so a
            # filtered query still describes the whole group. Matching on the
            # bucket-key expression (rather than base_experiment_id) is what
            # picks up letterless '-t' vials; it costs a scan per page row,
            # which is fine at this table's size and matches the existing
            # per-row queries in _build_list_item.
            bucket_rows = db.execute(
                select(Experiment)
                .where(_bucket_key_expr(Experiment) == bucket_key)
                .order_by(
                    Experiment.replicate_label.asc().nulls_first(),
                    Experiment.id_timepoint_days.asc().nulls_first(),
                    Experiment.experiment_number.asc(),
                )
            ).scalars().all()
            members = [m for m in bucket_rows if m.replicate_label is not None]
            item_data["vial_count"] = len(bucket_rows)

            if len(bucket_rows) > 1 and members:
                # A real group: label the row by the group stem (issue #98 D2).
                item_data["group_display_id"] = bucket_key
                item_data["replicate_letters"] = sorted(
                    {m.replicate_label for m in members}
                )
                # One child per letter-row, collapsed on the timepoint stem
                # (D1/D12) -- so SERUM_001a + SERUM_001a-t3 is one child, while
                # SERUM_001a-2 stays its own. Includes the representative's own
                # letter (D8), unlike the pre-#98 siblings-only list.
                item_data["replicates"] = []
                for group in collapse_by_stem(members):
                    child = _build_list_item(db, group.representative)
                    child["group_display_id"] = group.stem
                    child["vial_count"] = group.vial_count
                    item_data["replicates"].append(
                        ExperimentListItem.model_validate(child)
                    )
            else:
                # Not a group (standalone row, or a lone vial): show this row's
                # own stem so the '-t' token still never reaches the UI.
                item_data["group_display_id"] = split_timepoint_token(
                    exp.experiment_id
                )[0]
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


def _group_member_to_detail(member) -> ReplicateGroupMemberDetail:
    """Map a GroupMemberData (backend/services/replicate_groups.py) to the
    API schema. `conditions` carries ONLY the group's divergent fields for
    this member — shared fields live on the parent response instead."""
    exp = member.experiment
    return ReplicateGroupMemberDetail(
        id=exp.id,
        experiment_id=exp.experiment_id,
        replicate_label=exp.replicate_label,
        status=exp.status,
        is_outlier=exp.is_outlier,
        id_timepoint_days=exp.id_timepoint_days,
        researcher=exp.researcher,
        date=exp.date,
        result_count=member.result_count,
        conditions=member.divergent_conditions,
    )


def _group_data_to_detail_response(group: GroupData) -> ReplicateGroupDetailResponse:
    return ReplicateGroupDetailResponse(
        base_experiment_id=group.base_experiment_id,
        parent=ReplicateGroupMember.model_validate(group.parent) if group.parent else None,
        members=[_group_member_to_detail(m) for m in group.members],
        member_count=len(group.members),
        shared_conditions=group.shared_conditions,
        divergent_fields=group.divergent_fields,
        additives_summary=group.additives_summary,
        additive_names=group.additive_names,
        additives_diverge=group.additives_diverge,
    )


# NOTE: these two routes MUST stay registered before any "/{experiment_id}..."
# route below — FastAPI matches in declaration order, and /{experiment_id}
# would otherwise capture the literal path segment "groups".
@router.get("/groups/{base_id}", response_model=ReplicateGroupDetailResponse)
def get_replicate_group_detail(
    base_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ReplicateGroupDetailResponse:
    """The full replicate group for a base-ID string.

    Addressed by string, not by row: `base_id` need not name an experiment
    (lettered-only replicate sets with no group-parent row are the common
    case). 404 only when base_id matches neither an experiment row nor any
    base_experiment_id value.
    """
    group = resolve_group(db, base_id)
    if group.parent is None and not group.members:
        raise HTTPException(status_code=404, detail="Replicate group not found")
    return _group_data_to_detail_response(group)


@router.get("/groups/{base_id}/rollup", response_model=list[RollupTimepointResponse])
def get_group_rollup(
    base_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[RollupTimepointResponse]:
    """Cross-replicate mean/median/std per timepoint for a base-ID string."""
    if not group_exists(db, base_id):
        raise HTTPException(status_code=404, detail="Replicate group not found")
    rows = resolve_rollup_rows(db, base_id)
    return [RollupTimepointResponse(**dict(r)) for r in rows]


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
            h2_concentration=scalar.h2_concentration if scalar else None,
            h2_grams_per_ton_yield=scalar.h2_grams_per_ton_yield if scalar else None,
            h2_micromoles=scalar.h2_micromoles if scalar else None,
            gross_ammonium_concentration_mM=scalar.gross_ammonium_concentration_mM if scalar else None,
            background_ammonium_concentration_mM=scalar.background_ammonium_concentration_mM if scalar else None,
            final_conductivity_mS_cm=scalar.final_conductivity_mS_cm if scalar else None,
            final_ph=scalar.final_ph if scalar else None,
            scalar_measurement_date=scalar.measurement_date if scalar else None,
            ferrous_iron_yield_h2_pct=scalar.ferrous_iron_yield_h2_pct if scalar else None,
            ferrous_iron_yield_nh3_pct=scalar.ferrous_iron_yield_nh3_pct if scalar else None,
            nmr_run_date=scalar.nmr_run_date if scalar else None,
            icp_run_date=scalar.icp_run_date if scalar else None,
            gc_run_date=scalar.gc_run_date if scalar else None,
            xrd_run_date=scalar.xrd_run_date if scalar else None,
        ))
    return out


@router.get("/{experiment_id}/rollup", response_model=list[RollupTimepointResponse])
def get_experiment_rollup(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[RollupTimepointResponse]:
    """Cross-replicate mean/median/std per timepoint from v_results_scalar_rollup."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    base = exp.base_experiment_id or exp.experiment_id
    rows = resolve_rollup_rows(db, base)
    return [RollupTimepointResponse(**dict(r)) for r in rows]


@router.get("/{experiment_id}/replicate-group", response_model=ReplicateGroupResponse)
def get_replicate_group(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ReplicateGroupResponse:
    """The lettered replicate set this experiment belongs to (empty members if none).

    NOTE: deliberately NOT delegated to replicate_groups.resolve_group() —
    review of issue #87 found that resolving by base-ID string diverges from
    this endpoint's original row-relative resolution for a plain sequential/
    treatment derivation with no letter (e.g. "SERUM_001-2"): the old logic
    treats such a row as its own "parent" with no members, while resolving
    by base string would surface the unrelated lettered a/b/c set under the
    same stem. The issue owner decided to preserve the original behavior
    byte-for-byte here; only /groups/{base_id} uses resolve_group(). See
    tests/api/test_experiment_rollup.py::TestReplicateGroupWrapperShapes for
    the locked-in regression coverage.
    """
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    base = exp.base_experiment_id or exp.experiment_id
    parent = exp if exp.replicate_label is None else exp.parent
    if parent is not None:
        members = db.execute(
            select(Experiment)
            .where(
                Experiment.parent_experiment_fk == parent.id,
                Experiment.replicate_label.isnot(None),
            )
            .order_by(Experiment.replicate_label.asc())
        ).scalars().all()
    else:
        # Orphan member: parent row doesn't exist yet; list siblings by base stem.
        members = db.execute(
            select(Experiment)
            .where(
                Experiment.base_experiment_id == base,
                Experiment.replicate_label.isnot(None),
            )
            .order_by(Experiment.replicate_label.asc())
        ).scalars().all()
    return ReplicateGroupResponse(
        base_experiment_id=base,
        parent=ReplicateGroupMember.model_validate(parent) if parent else None,
        members=[ReplicateGroupMember.model_validate(m) for m in members],
    )


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


@router.get("/{experiment_id}/change-requests", response_model=list[ChangeRequestResponse])
def list_change_requests(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> list[ChangeRequestResponse]:
    """List change request entries linked to this experiment. Returns [] if none."""
    exp = db.execute(
        select(Experiment.id).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    rows = db.execute(
        select(ReactorChangeRequest)
        .where(ReactorChangeRequest.experiment_id == experiment_id)
        .order_by(ReactorChangeRequest.sync_date.desc())
    ).scalars().all()
    return [ChangeRequestResponse.model_validate(r) for r in rows]


@router.get("/{experiment_id}/change-requests/recent", response_model=RecentChangeRequestsResponse)
def get_recent_change_requests(
    experiment_id: str,
    on_date: date = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> RecentChangeRequestsResponse:
    """Return this experiment's modification entry for `date` (default today) and the
    most recent prior entry, both scoped to this experiment_id only — never another
    experiment that previously occupied the same physical reactor.
    """
    exp = db.execute(
        select(Experiment.id).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    target_date = on_date or date.today()

    selected_row = db.execute(
        select(ReactorChangeRequest).where(
            ReactorChangeRequest.experiment_id == experiment_id,
            ReactorChangeRequest.sync_date == target_date,
        )
    ).scalar_one_or_none()

    previous_row = db.execute(
        select(ReactorChangeRequest)
        .where(
            ReactorChangeRequest.experiment_id == experiment_id,
            ReactorChangeRequest.sync_date < target_date,
        )
        .order_by(ReactorChangeRequest.sync_date.desc())
        .limit(1)
    ).scalar_one_or_none()

    return RecentChangeRequestsResponse(
        selected=ChangeRequestResponse.model_validate(selected_row) if selected_row else None,
        previous=ChangeRequestResponse.model_validate(previous_row) if previous_row else None,
    )


@router.post("/{experiment_id}/change-requests", response_model=ChangeRequestResponse)
def upsert_change_request(
    experiment_id: str,
    payload: ChangeRequestUpsertRequest,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ChangeRequestResponse:
    """Create or update a reactor modification entry for a given reactor + date.

    Upserts on the unique constraint (reactor_label, experiment_id, sync_date): if a
    row already exists for this reactor, experiment, and date, its requested_change
    is overwritten. Defaults sync_date to today if omitted. Returns the persisted
    record. Returns 422 if requested_change is blank; 404 if the experiment does
    not exist.
    """
    if not payload.requested_change.strip():
        raise HTTPException(status_code=422, detail="requested_change must not be blank")

    exp = db.execute(
        select(Experiment.id).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    sync_date = payload.sync_date or date.today()
    stmt = (
        pg_insert(ReactorChangeRequest)
        .values(
            reactor_label=payload.reactor_label,
            experiment_id=experiment_id,
            requested_change=payload.requested_change.strip(),
            sync_date=sync_date,
            notion_page_id=None,
            notion_status=None,
            carried_forward=False,
        )
        .on_conflict_do_update(
            constraint="uq_change_request_reactor_experiment_date",
            set_={
                "requested_change": payload.requested_change.strip(),
            },
        )
    )
    db.execute(stmt)
    db.commit()

    record = db.execute(
        select(ReactorChangeRequest).where(
            ReactorChangeRequest.reactor_label == payload.reactor_label,
            ReactorChangeRequest.experiment_id == experiment_id,
            ReactorChangeRequest.sync_date == sync_date,
        )
    ).scalar_one()
    log.info(
        "change_request_upserted",
        experiment_id=experiment_id,
        reactor_label=payload.reactor_label,
        sync_date=str(sync_date),
    )
    return ChangeRequestResponse.model_validate(record)


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


@router.post("/replicates", response_model=ReplicateCreateResponse, status_code=201)
def create_replicates(
    payload: ReplicateCreateRequest,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> ReplicateCreateResponse:
    """Batch-create lettered replicates copying the base experiment's setup."""
    from database.lineage_utils import create_replicate_experiments

    try:
        created, skipped = create_replicate_experiments(
            db, payload.base_experiment_id, payload.count
        )
        db.commit()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Replicate ID conflict on creation")
    for exp in created:
        db.refresh(exp)
    log.info(
        "replicates_created",
        base_experiment_id=payload.base_experiment_id,
        created=[e.experiment_id for e in created],
        skipped=skipped,
        user=current_user.email,
    )
    return ReplicateCreateResponse(
        created=[ExperimentResponse.model_validate(e) for e in created],
        skipped=skipped,
    )


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
    new_sample_id = data.pop("sample_id", None)
    old_date = exp.date  # capture before mutation
    old_is_outlier = exp.is_outlier  # capture before mutation

    for field, value in data.items():
        setattr(exp, field, value)

    if "date" in data:
        db.add(ModificationsLog(
            experiment_id=exp.experiment_id,
            experiment_fk=exp.id,
            modified_by=current_user.uid,
            modification_type="update",
            modified_table="experiments",
            old_values={"date": old_date.isoformat() if old_date else None},
            new_values={"date": data["date"].isoformat() if data["date"] else None},
        ))
        log.info("experiment_date_updated", experiment_id=exp.experiment_id, user=current_user.uid)

    if "is_outlier" in data and data["is_outlier"] != old_is_outlier:
        db.add(ModificationsLog(
            experiment_id=exp.experiment_id,
            experiment_fk=exp.id,
            modified_by=current_user.uid,
            modification_type="update",
            modified_table="experiments",
            old_values={"is_outlier": old_is_outlier},
            new_values={"is_outlier": data["is_outlier"]},
        ))
        log.info("experiment_outlier_updated", experiment_id=exp.experiment_id,
                 is_outlier=data["is_outlier"], user=current_user.uid)

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

            from database.lineage_utils import (
                update_experiment_lineage, update_orphaned_derivations, parse_experiment_id,
            )

            # Issue #87 (D3, locked decision 5): block renaming a group parent
            # that has lettered replicates. Only fires when the OLD id is
            # ITSELF a group-parent spelling (bare stem, or explicit -0/-1) —
            # gating on the parsed spelling, not just base_experiment_id,
            # keeps this from over-firing on renames of lettered members
            # (e.g. SERUM_040a) or sequential re-runs (e.g. SERUM_040-2),
            # which are never parents and must remain allowed. A -0/-1-spelled
            # parent shares its lettered members' base_experiment_id (the bare
            # stem), not its own literal id string, so the member query below
            # must use the parsed stem, not the raw path param.
            old_base, old_deriv, old_treat, old_letter = parse_experiment_id(experiment_id)
            if _is_group_parent_spelling(old_deriv, old_treat, old_letter):
                old_stem = old_base or experiment_id
                member_ids = db.execute(
                    select(Experiment.experiment_id).where(
                        Experiment.base_experiment_id == old_stem,
                        Experiment.replicate_label.isnot(None),
                        Experiment.id != exp.id,
                    )
                ).scalars().all()
                if member_ids:
                    log.warning(
                        "experiment_rename_blocked_group_parent",
                        experiment_id=experiment_id,
                        members=sorted(member_ids),
                        user=current_user.uid,
                    )
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Cannot rename group parent '{experiment_id}': it has lettered "
                            f"replicate(s) {sorted(member_ids)}; renaming would orphan them."
                        ),
                    )

            exp.experiment_id = new_id
            # Issue #87 (D3): persist the new id BEFORE recomputing lineage.
            # Production SessionLocal has autoflush=False (same as tests/api's
            # session factory), so without this flush update_experiment_lineage's
            # group-parent SELECT can match this row against its own stale
            # (old) experiment_id — the exact issue #86 ordering bug. Mirrors
            # the bulk-upload rename precedent (new_experiments.py:385-392).
            db.flush()
            update_experiment_lineage(db, exp)

            # If the new spelling is itself a group-parent spelling (no
            # treatment, no letter, sequential in {None, 0, 1}), back-link any
            # pre-existing orphaned derivations of that stem to this row.
            new_base_id, new_derivation_num, new_treatment, new_replicate_label = (
                parse_experiment_id(new_id)
            )
            is_new_parent_spelling = _is_group_parent_spelling(
                new_derivation_num, new_treatment, new_replicate_label
            )
            if is_new_parent_spelling:
                new_stem = new_base_id or new_id
                backlinked = update_orphaned_derivations(db, new_stem)
                if backlinked:
                    log.info(
                        "experiment_rename_backlinked_orphans",
                        new_id=new_id,
                        stem=new_stem,
                        count=backlinked,
                        user=current_user.uid,
                    )
            # Keep denormalized string in conditions in sync so additives endpoints work
            cond = db.execute(
                select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
            ).scalar_one_or_none()
            if cond is not None:
                cond.experiment_id = new_id
            # Sync denormalized experiment_id across all tables that carry it
            db.execute(
                update(ExperimentNotes)
                .where(ExperimentNotes.experiment_fk == exp.id)
                .values(experiment_id=new_id)
            )
            db.execute(
                update(ExternalAnalysis)
                .where(ExternalAnalysis.experiment_fk == exp.id)
                .values(experiment_id=new_id)
            )
            db.execute(
                update(XRDPhase)
                .where(XRDPhase.experiment_fk == exp.id)
                .values(experiment_id=new_id)
            )
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

    if new_sample_id is not None:
        sample = db.get(SampleInfo, new_sample_id)
        if sample is None:
            raise HTTPException(status_code=404, detail=f"Sample '{new_sample_id}' not found")
        old_sample_id = exp.sample_id
        exp.sample_id = new_sample_id
        db.flush()
        cond = db.execute(
            select(ExperimentalConditions).where(ExperimentalConditions.experiment_fk == exp.id)
        ).scalar_one_or_none()
        if cond is not None:
            recalculate(cond, db)
            db.flush()
        # Also recalculate scalars directly: conditions_calcs.py cascades to scalars via ORM
        # relationships when conditions exist, but this explicit loop ensures scalars update
        # even when there are no conditions (total_ferrous_iron_g stays NULL in that case).
        result_ids = db.execute(
            select(ExperimentalResults.id).where(ExperimentalResults.experiment_fk == exp.id)
        ).scalars().all()
        scalars = db.execute(
            select(ScalarResults).where(ScalarResults.result_id.in_(result_ids))
        ).scalars().all()
        for scalar in scalars:
            recalculate(scalar, db)
        db.add(ModificationsLog(
            experiment_id=exp.experiment_id,
            experiment_fk=exp.id,
            modified_by=current_user.uid,
            modification_type="update",
            modified_table="experiments",
            old_values={"sample_id": old_sample_id},
            new_values={"sample_id": new_sample_id},
        ))
        log.info("experiment_sample_updated", experiment_id=exp.experiment_id, new_sample_id=new_sample_id, user=current_user.uid)

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


@router.delete("/{experiment_id}/notes/{note_id}", status_code=204)
def delete_note(
    experiment_id: str,
    note_id: int,
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> Response:
    """Delete a note. Writes a ModificationsLog entry then removes the row."""
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
    db.add(ModificationsLog(
        experiment_id=experiment_id,
        experiment_fk=exp.id,
        modified_by=current_user.email,
        modification_type="delete",
        modified_table="experiment_notes",
        old_values={"note_text": note.note_text},
        new_values=None,
    ))
    db.delete(note)
    db.commit()
    log.info("note_deleted", experiment_id=experiment_id, note_id=note_id)
    return Response(status_code=204)
