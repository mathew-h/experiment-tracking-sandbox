"""Serum-vial H2 background links (issue #144).

A sample group (base experiment) is linked to a background either as a whole
replicate group ("group" mode, background_base_id) or one vial stem ("vial"
mode, background_stem_id; the '-t<days>' token peeled off). The service never
commits; the router owns the transaction.
"""
from __future__ import annotations

from typing import Literal, Mapping

from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from database.experiment_id_parser import split_timepoint_token
from database.models import H2BackgroundLink
from database.models.experiments import Experiment, ModificationsLog
from database.models.results import ExperimentalResults, ScalarResults
from backend.services.experiment_lookup import find_experiment, series_key
from backend.services.replicate_collapse import timepoint_stem_expr

LinkMode = Literal["group", "vial"]
_TABLE = "h2_background_links"


# Kept under its original name for this module's callers.
group_key = series_key


def get_link(db: Session, base_id: str) -> H2BackgroundLink | None:
    return db.execute(
        select(H2BackgroundLink).where(H2BackgroundLink.base_experiment_id == base_id)
    ).scalar_one_or_none()


def link_mode(link: H2BackgroundLink) -> LinkMode:
    return "group" if link.background_base_id is not None else "vial"


def link_ref(link: H2BackgroundLink) -> str:
    if link.background_base_id is not None:
        return link.background_base_id
    return link.background_stem_id


def _has_usable_background(db: Session, mode: LinkMode, ref: str) -> bool:
    """Mirror the view's bm/bsel/bkg CTEs: primary row, non-null H2 and bucket,
    non-outlier experiment; and when the set has any non-outlier
    is_background vial, only those count (issue #152)."""
    if mode == "group":
        key = func.coalesce(Experiment.base_experiment_id, Experiment.experiment_id)
        match = key == ref
    else:
        match = timepoint_stem_expr(Experiment) == ref
    not_outlier = func.coalesce(Experiment.is_outlier, False).is_(False)
    has_flagged = db.execute(
        select(Experiment.id).where(match, not_outlier, Experiment.is_background.is_(True)).limit(1)
    ).first() is not None
    if has_flagged:
        match = and_(match, Experiment.is_background.is_(True))
    q = (
        select(ExperimentalResults.id)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .join(ScalarResults, ScalarResults.result_id == ExperimentalResults.id)
        .where(
            match,
            ExperimentalResults.is_primary_timepoint_result.is_(True),
            ScalarResults.h2_micromoles.is_not(None),
            ExperimentalResults.time_post_reaction_bucket_days.is_not(None),
            not_outlier,
        )
        .limit(1)
    )
    return db.execute(q).first() is not None


def set_link(db: Session, base_id: str, experiment_id: str, mode: LinkMode,
             user_email: str) -> H2BackgroundLink:
    bg_exp = find_experiment(db, experiment_id)
    if bg_exp is None:
        raise LookupError(f"Experiment '{experiment_id}' not found")
    if group_key(bg_exp) == base_id:
        raise ValueError("A group cannot be its own H2 background")

    if mode == "group":
        ref = group_key(bg_exp)
    else:
        ref = split_timepoint_token(experiment_id)[0]
    if not _has_usable_background(db, mode, ref):
        raise ValueError(
            f"Background '{ref}' has no primary H2 (micromoles) results with a "
            "time bucket on a non-outlier experiment"
        )

    link = get_link(db, base_id)
    new_vals = {"mode": mode, "background_ref": ref}
    if link is None:
        old_vals = None
        mod_type = "create"
        link = H2BackgroundLink(base_experiment_id=base_id, created_by=user_email)
        db.add(link)
    else:
        old_vals = {"mode": link_mode(link), "background_ref": link_ref(link)}
        mod_type = "update"
    link.background_base_id = ref if mode == "group" else None
    link.background_stem_id = ref if mode == "vial" else None
    db.add(ModificationsLog(
        experiment_id=base_id, experiment_fk=None, modified_by=user_email,
        modification_type=mod_type, modified_table=_TABLE,
        old_values=old_vals, new_values=new_vals,
    ))
    db.flush()
    db.refresh(link)
    return link


def clear_link(db: Session, base_id: str, user_email: str) -> bool:
    link = get_link(db, base_id)
    if link is None:
        return False
    old_vals = {"mode": link_mode(link), "background_ref": link_ref(link)}
    db.delete(link)
    db.add(ModificationsLog(
        experiment_id=base_id, experiment_fk=None, modified_by=user_email,
        modification_type="delete", modified_table=_TABLE,
        old_values=old_vals, new_values=None,
    ))
    db.flush()
    return True


def rollup_rows(db: Session, base_id: str) -> list[Mapping]:
    return list(db.execute(text(
        "SELECT * FROM v_results_h2_bkg_adjusted_rollup "
        "WHERE base_experiment_id = :b ORDER BY time_post_reaction_bucket_days"
    ), {"b": base_id}).mappings())


def groups_using_background(db: Session, exp: Experiment) -> list[str]:
    stem = split_timepoint_token(exp.experiment_id)[0]
    rows = db.execute(
        select(H2BackgroundLink.base_experiment_id).where(
            (H2BackgroundLink.background_base_id == group_key(exp))
            | (H2BackgroundLink.background_stem_id == stem)
        )
    ).scalars().all()
    return sorted(rows)
