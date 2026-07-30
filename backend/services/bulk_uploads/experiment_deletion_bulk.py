"""Bulk experiment deletion from an uploaded ID list (issue #109, Phase 1).

A batch wrapper around `experiment_deletion.delete_experiment_cascade` -- the
per-experiment purge, its decoupling rules and its ModificationsLog audit row all
stay there and are not reimplemented or altered here (see MODELS.md, issue #99).

Phase 1 deliberately has no preview, no dry_run and no plan_hash gate: the
endpoint is restricted to a single trusted user cleaning up a known list of bad
entries, and partial success on a bad batch beats an all-or-nothing rollback.
`delete_experiment_cascade` commits per row, which is what makes that partial
success durable.

**Per-row isolation is a SAVEPOINT, not `db.rollback()`.** One unusable row must
not abort the batch, and after a failed statement Postgres refuses every
subsequent statement until the transaction is unwound -- so something has to
unwind it. A session-wide `db.rollback()` would also discard every experiment
already deleted in this batch (they are committed in the same session), turning
one bad row into a silent no-op for the good ones. `begin_nested()` per row
unwinds only the failing row and leaves the session usable.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.services.experiment_deletion import delete_experiment_cascade
from database.models.experiments import Experiment

log = structlog.get_logger(__name__)

ID_COLUMN = "experiment_id"


@dataclass
class BulkDeleteResult:
    """Outcome of one uploaded deletion list.

    deleted / missing preserve the order the IDs appeared in the file. `errors`
    holds file-level problems (unreadable file, absent ID column, empty list) --
    when it is non-empty nothing was deleted.
    """

    deleted: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    failed: list[dict[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _normalize_header(column: object) -> str:
    """'Experiment ID' / ' experiment_id ' -> 'experiment_id'."""
    return " ".join(str(column).strip().lower().split()).replace(" ", "_")


def _read_frame(file_bytes: bytes, filename: str | None) -> pd.DataFrame:
    """Read the upload as CSV or Excel, choosing by extension and falling back."""
    is_csv = (filename or "").lower().endswith(".csv")
    readers = (
        [pd.read_csv, pd.read_excel] if is_csv else [pd.read_excel, pd.read_csv]
    )
    last_error: Exception | None = None
    for reader in readers:
        try:
            return reader(io.BytesIO(file_bytes))
        except Exception as exc:  # noqa: PERF203 — two attempts, not a hot loop
            last_error = exc
    raise ValueError(f"Failed to read file: {last_error}")


def parse_experiment_ids(
    file_bytes: bytes, filename: str | None = None
) -> tuple[list[str], list[str]]:
    """Extract the experiment_id column: deduped, blank rows dropped, order kept.

    Returns (ids, errors). A non-empty `errors` means the file could not be used
    at all -- caller must not delete anything.
    """
    try:
        df = _read_frame(file_bytes, filename)
    except ValueError as exc:
        return [], [str(exc)]

    col_map = {_normalize_header(c): c for c in df.columns}
    if ID_COLUMN not in col_map:
        return [], [
            f"Missing required column: '{ID_COLUMN}'. Found: "
            f"{', '.join(str(c) for c in df.columns) or '(no columns)'}"
        ]

    ids: list[str] = []
    seen: set[str] = set()
    for raw in df[col_map[ID_COLUMN]]:
        if pd.isna(raw):
            continue
        experiment_id = str(raw).strip()
        if not experiment_id or experiment_id in seen:
            continue
        seen.add(experiment_id)
        ids.append(experiment_id)

    return ids, []


def delete_experiments_from_file(
    db: Session,
    file_bytes: bytes,
    filename: str | None = None,
    modified_by: str | None = None,
) -> BulkDeleteResult:
    """Hard-delete every experiment named in the uploaded file.

    Each row is purged by `delete_experiment_cascade`, which commits. A row that
    cannot be deleted is unwound to its SAVEPOINT and recorded in `failed`; the
    rest of the batch continues. IDs with no matching experiment go to `missing`
    rather than failing the request -- a typo in one row must not block a cleanup.
    """
    ids, errors = parse_experiment_ids(file_bytes, filename)
    if errors:
        return BulkDeleteResult(errors=errors)
    if not ids:
        return BulkDeleteResult(errors=[f"No {ID_COLUMN} values found in file"])

    known = set(db.execute(
        select(Experiment.experiment_id).where(Experiment.experiment_id.in_(ids))
    ).scalars().all())

    result = BulkDeleteResult(missing=[i for i in ids if i not in known])

    for experiment_id in (i for i in ids if i in known):
        savepoint = db.begin_nested()
        try:
            # Re-read per row: the previous row's commit expired the identity map,
            # and a concurrent delete may have removed this one in the meantime.
            exp = db.execute(
                select(Experiment).where(Experiment.experiment_id == experiment_id)
            ).scalar_one_or_none()
            if exp is None:
                if savepoint.is_active:
                    savepoint.rollback()
                result.missing.append(experiment_id)
                continue
            delete_experiment_cascade(db, exp, modified_by=modified_by)
            result.deleted.append(experiment_id)
        except Exception as exc:
            # SAVEPOINT, not db.rollback(): see the module docstring.
            if savepoint.is_active:
                savepoint.rollback()
            result.failed.append({"experiment_id": experiment_id, "error": str(exc)})
            log.error("bulk_experiment_delete_row_failed",
                      experiment_id=experiment_id, user=modified_by, error=str(exc))

    log.info(
        "bulk_experiment_delete_complete",
        user=modified_by,
        deleted=len(result.deleted),
        missing=len(result.missing),
        failed=len(result.failed),
    )
    return result
