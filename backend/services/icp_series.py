"""ICP-OES readings over time for a series (issues #140, #143). Read-only.

Reads icp_results directly rather than v_results_icp, which has no s_ppm.
Only primary timepoint results are plotted, as in v_core_flood_samples.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.api.schemas.results import (
    ICP_ELEMENTS, ExperimentIcpResponse, IcpRow, IcpSegmentStart,
)
from database.models.experiments import Experiment

# Element columns of icp_results aliased as icp_<el>; join alias must be `i`.
ICP_SELECT = ", ".join(f'i."{e}" AS "icp_{e}"' for e in ICP_ELEMENTS)

# A `_Text` child of its parent (CF_020-5_Bypass1 under CF_020-5): a blank or
# bypass, never a segment. Same rule as v_core_flood_samples.is_variant.
_IS_VARIANT = (
    "COALESCE(p.experiment_id IS NOT NULL"
    " AND left(e.experiment_id, length(p.experiment_id) + 1)"
    " = p.experiment_id || '_', false)"
)

# Primary results of every experiment in the series (base ID, else own ID).
_FROM = (
    " FROM experimental_results er"
    " JOIN experiments e ON e.id = er.experiment_fk"
    " LEFT JOIN experiments p ON p.id = e.parent_experiment_fk"
)
_WHERE = (
    " WHERE COALESCE(e.base_experiment_id, e.experiment_id) = :base"
    " AND er.is_primary_timepoint_result = TRUE"
)


class ExperimentNotFound(LookupError):
    pass


def icp_rows(mappings: Iterable[Mapping[str, Any]]) -> list[IcpRow]:
    """Rows selecting result_id, experiment_id, is_variant,
    cumulative_time_post_reaction_days, sample_date and ICP_SELECT."""
    return [
        IcpRow(
            result_id=r["result_id"],
            experiment_id=r["experiment_id"],
            is_variant=r["is_variant"],
            cumulative_time_post_reaction_days=r["cumulative_time_post_reaction_days"],
            sample_date=r["sample_date"],
            elements={e: float(r[f"icp_{e}"]) for e in ICP_ELEMENTS
                      if r[f"icp_{e}"] is not None},
        )
        for r in mappings
    ]


def series_icp(db: Session, experiment_id: str) -> ExperimentIcpResponse:
    """ICP readings for every experiment sharing the requested one's base ID
    (the experiment alone when it has none), ordered by cumulative day, plus
    the start day of each chained segment. Serum vials (-tN) have no parent,
    so a vial set plots as one curve without markers."""
    exp = db.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()
    if exp is None:
        raise ExperimentNotFound(experiment_id)
    params = {"base": exp.base_experiment_id or exp.experiment_id}
    rows = icp_rows(db.execute(text(
        "SELECT er.id AS result_id, e.experiment_id, " + _IS_VARIANT + " AS is_variant,"
        " er.cumulative_time_post_reaction_days, sr.measurement_date AS sample_date, "
        + ICP_SELECT + _FROM +
        " JOIN icp_results i ON i.result_id = er.id"
        " LEFT JOIN scalar_results sr ON sr.result_id = er.id"
        + _WHERE +
        " ORDER BY er.cumulative_time_post_reaction_days NULLS LAST, er.id"
    ), params).mappings())
    starts = [
        IcpSegmentStart(experiment_id=r["experiment_id"], day=r["day"])
        for r in db.execute(text(
            "SELECT e.experiment_id, MIN(er.cumulative_time_post_reaction_days) AS day"
            + _FROM + _WHERE +
            " AND p.id IS NOT NULL AND NOT " + _IS_VARIANT +
            " AND er.cumulative_time_post_reaction_days IS NOT NULL"
            " GROUP BY e.experiment_id ORDER BY day, e.experiment_id"
        ), params).mappings()
    ]
    return ExperimentIcpResponse(rows=rows, segment_starts=starts)
