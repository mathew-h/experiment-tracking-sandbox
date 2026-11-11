"""Throwaway ground-truth comparison for issue #168 Part 1 (not committed unless agreed).

Rebuilds a Data Export workbook's experiment set against the restored
2026-11-06 dump (experiments_audit168) using the export service's own row
builders, and diffs each tab's grain keys against the workbook.

Usage (repo root): PYTHONPATH=. .venv/Scripts/python docs/working/export_audit/compare.py <xlsx>
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent))
from auditdb import engine  # noqa: E402

from backend.services import experiment_export as ex  # noqa: E402

CUTOFF = "2026-11-06"


def wb_keys(ws, cols):
    header = [c.value for c in ws[1]]
    idx = [header.index(c) for c in cols]
    return [tuple(r[i] for i in idx) for r in ws.iter_rows(min_row=2, values_only=True)
            if any(v is not None for v in r)]


def main(path: str) -> None:
    wb = load_workbook(path, read_only=True)
    ids = [r[0] for r in wb["Experiments"].iter_rows(min_row=2, values_only=True) if r[0]]
    include = dict(r[:2] for r in wb["Summary"].iter_rows(min_row=2, values_only=True)
                   )["Include whole series"] == "Yes"

    with Session(engine) as db:
        present = set(db.execute(text(
            "SELECT experiment_id FROM experiments WHERE experiment_id = ANY(:i)"),
            {"i": ids}).scalars())
        absent = [i for i in ids if i not in present]
        print(f"workbook experiments: {len(ids)}; in 11-06 dump: {len(present)}; "
              f"absent (drift): {len(absent)} {absent[:20]}")

        members = ex.resolve_selection(db, sorted(present), include)
        print(f"resolve_selection -> {len(members)} members "
              f"(extra vs workbook: {sorted(set(m.experiment_id for m in members) - set(ids))[:10]})")

        results, _ = ex.results_rows(db, members)
        cf = ex.core_flood_rows(db, members) if any(m.is_core_flood for m in members) else []
        xrd, _ = ex.xrd_rows(db, members)
        rock, _ = ex.rock_xrd_rows(db, members)
        cond = ex.condition_rows(db, members)
        add = ex.additive_rows(db, members)
        notes = ex.note_rows(db, members)

        expected = {
            "Experiments": [(m.experiment_id,) for m in members],
            "Results": [(r["result_id"],) for r in results],
            "Core Flood": [(r["result_id"],) for r in cf],
            "XRD": [(r["experiment_id"], r["time_post_reaction_days"]) for r in xrd],
            "Rock XRD": [(r["sample_id"],) for r in rock],
            "Conditions": [(r["experiment_id"],) for r in cond],
            "Additives": [(r["experiment_id"], r["compound_name"]) for r in add],
            "Notes": [(r["note_id"],) for r in notes],
        }
        grain = {
            "Experiments": ["Experiment ID"], "Results": ["Result ID"],
            "Core Flood": ["Result ID"], "XRD": ["Experiment ID", "Day"],
            "Rock XRD": ["Sample ID"], "Conditions": ["Experiment ID"],
            "Additives": ["Experiment ID", "Compound"], "Notes": ["Note ID"],
        }
        print(f"\n{'tab':<12}{'workbook':>9}{'dump':>7}  only-in-workbook / only-in-dump")
        for tab, cols in grain.items():
            actual = Counter(wb_keys(wb[tab], cols)) if tab in wb.sheetnames else Counter()
            exp = Counter(expected[tab])
            only_wb = sorted((actual - exp).elements(), key=str)
            only_db = sorted((exp - actual).elements(), key=str)
            print(f"{tab:<12}{sum(actual.values()):>9}{sum(exp.values()):>7}  "
                  f"+{len(only_wb)} {only_wb[:6]} / -{len(only_db)} {only_db[:6]}")

        # Silent-merge probes (B1, B2) over the members.
        fks = [m.id for m in members]
        for v in ("v_results_scalar", "v_results_h2", "v_results_icp"):
            n = db.execute(text(f"SELECT count(*) FROM (SELECT result_id FROM {v} "
                                "WHERE experiment_fk = ANY(:f) GROUP BY result_id "
                                "HAVING count(*) > 1) d"), {"f": fks}).scalar()
            print(f"B1 {v}: result_ids with >1 row = {n}")
        n = db.execute(text("SELECT count(*) FROM (SELECT t.result_id FROM v_dim_timepoints t "
                            "JOIN experimental_results er ON er.id = t.result_id "
                            "WHERE er.experiment_fk = ANY(:f) GROUP BY t.result_id "
                            "HAVING count(*) > 1) d"), {"f": fks}).scalar()
        print(f"B1 v_dim_timepoints: result_ids with >1 row = {n}")
        sql_b2 = ("SELECT experiment_id, time_post_reaction_days, count(DISTINCT "
                  "(measurement_date, rwp)) n FROM v_experiment_xrd "
                  "WHERE experiment_id = ANY(:i) GROUP BY 1, 2 "
                  "HAVING count(DISTINCT (measurement_date, rwp)) > 1")
        print("B2 XRD (exp, day) with >1 scan:",
              db.execute(text(sql_b2), {"i": [m.experiment_id for m in members]}).all())
        # B4: non-primary results hidden from Results.
        n = db.execute(text("SELECT count(*) FROM experimental_results WHERE "
                            "experiment_fk = ANY(:f) AND NOT is_primary_timepoint_result"),
                       {"f": fks}).scalar()
        print(f"B4 non-primary results excluded from Results: {n}")
        # Experiments with zero Results rows: do they have any result at all?
        no_res = db.execute(text(
            "SELECT e.experiment_id, count(er.id) n_all, "
            "count(er.id) FILTER (WHERE er.is_primary_timepoint_result) n_primary "
            "FROM experiments e LEFT JOIN experimental_results er ON er.experiment_fk = e.id "
            "WHERE e.id = ANY(:f) GROUP BY 1 HAVING count(er.id) FILTER "
            "(WHERE er.is_primary_timepoint_result) = 0 ORDER BY 1"), {"f": fks}).all()
        with_any = [r for r in no_res if r.n_all > 0]
        print(f"experiments with no primary result: {len(no_res)}; of those with "
              f"non-primary results only: {len(with_any)} {with_any[:10]}")
        # Results with a primary row but no scalar_results row (absent from v_results_scalar?)
        n = db.execute(text(
            "SELECT count(*) FROM experimental_results er WHERE er.experiment_fk = ANY(:f) "
            "AND er.is_primary_timepoint_result AND er.id NOT IN "
            "(SELECT result_id FROM v_results_scalar)"), {"f": fks}).scalar()
        print(f"primary results missing from v_results_scalar: {n}")


if __name__ == "__main__":
    main(sys.argv[1])
