"""
One-time cleanup: demote six stale primary result rows on '-t3' vials that sit
in the wrong timepoint bucket (day 6/7 instead of the ID-encoded day 3).

Background
----------
Before commit 9ea8962 (2026-07-30, "Let the ID -t token win over Duration
column"), the Master Results parser let the sheet's Duration column override the
'-t<days>' token in the experiment ID. Six vials ingested on 2026-07-28/29 under
the old rule landed at day 6/7.

Each of those six vials was re-uploaded after the fix and **already holds a
correct day-3 row** carrying the actual H2 reading. The stale rows are empty
shells: every scalar measurement column is NULL and no result files are
attached. They are still flagged ``is_primary_timepoint_result``, so they
contribute a phantom extra bucket to ``v_results_scalar_rollup`` -- this is what
inflated SERUM_pH_001's day-7 bucket to 5 vials in a group with 3 letters.

Why demote rather than re-bucket
--------------------------------
Setting these rows to day 3 would collide with the good day-3 row under
``uq_primary_result_per_experiment_bucket``. Demotion is the schema's own
mechanism for a superseded row: every reporting view filters on
``is_primary_timepoint_result``, so demoting removes them from all reporting
while leaving the rows recoverable.

Verified before writing this script (against the 2026-08-01 production backup):
all six rows have NULL for every scalar measurement column and zero result_files.

See docs/issues/issue-rollup-replicate-count-and-null-timepoint-buckets.md

Usage:
    # Dry run (preview only, no writes)
    python database/data_migrations/demote_stale_t3_prefix_rows_017.py

    # Apply
    python database/data_migrations/demote_stale_t3_prefix_rows_017.py --apply
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from database import get_db  # noqa: E402

# Selected by rule, not by hardcoded id: a primary row on a '-t' vial whose
# bucket disagrees with the ID's token, carrying no measurement at all, where a
# correct row for the ID's day already exists.
SELECT_STALE = """
    SELECT er.id, e.experiment_id, er.time_post_reaction_bucket_days,
           e.id_timepoint_days
    FROM experimental_results er
    JOIN experiments e ON e.id = er.experiment_fk
    JOIN scalar_results sr ON sr.result_id = er.id
    WHERE er.is_primary_timepoint_result = TRUE
      AND e.id_timepoint_days IS NOT NULL
      AND er.time_post_reaction_bucket_days IS DISTINCT FROM e.id_timepoint_days
      -- carries no measurement whatsoever
      AND sr."gross_ammonium_concentration_mM" IS NULL
      AND sr.final_ph IS NULL
      AND sr.h2_concentration IS NULL
      AND sr."final_conductivity_mS_cm" IS NULL
      AND sr."final_nitrate_concentration_mM" IS NULL
      AND sr."final_alkalinity_mg_L" IS NULL
      AND sr."final_dissolved_oxygen_mg_L" IS NULL
      AND sr.gas_sampling_volume_ml IS NULL
      AND sr."grams_per_ton_yield" IS NULL
      AND sr.ferrous_iron_yield IS NULL
      AND sr."sampling_volume_mL" IS NULL
      -- no files would be orphaned from reporting
      AND NOT EXISTS (SELECT 1 FROM result_files rf WHERE rf.result_id = er.id)
      -- a correct row for the ID's day already exists on this same vial
      AND EXISTS (
          SELECT 1 FROM experimental_results good
          WHERE good.experiment_fk = er.experiment_fk
            AND good.id <> er.id
            AND good.time_post_reaction_bucket_days = e.id_timepoint_days
      )
    ORDER BY er.id
"""


def main(apply: bool) -> None:
    db = next(get_db())
    try:
        from sqlalchemy import text

        rows = db.execute(text(SELECT_STALE)).mappings().all()

        if not rows:
            print("No stale '-t' primary rows found — nothing to do.")
            return

        print(f"Stale primary rows to demote: {len(rows)}\n")
        print(f"{'result_id':>10}  {'experiment_id':<20} {'bucket':>7} -> {'ID day':>6}")
        for r in rows:
            print(
                f"{r['id']:>10}  {r['experiment_id']:<20} "
                f"{r['time_post_reaction_bucket_days']:>7} -> {r['id_timepoint_days']:>6}"
            )

        if not apply:
            print("\nDry run — pass --apply to commit changes.")
            return

        ids = [r["id"] for r in rows]
        db.execute(
            text(
                "UPDATE experimental_results "
                "SET is_primary_timepoint_result = FALSE "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": ids},
        )
        db.commit()
        print(f"\nDemoted {len(ids)} row(s). They remain in the database but are "
              "excluded from every reporting view.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the changes")
    main(parser.parse_args().apply)
