"""Throwaway validator for issue #168 Part 1 (not committed unless agreed).

Usage: .venv/Scripts/python docs/working/export_audit/validate.py <xlsx> [...]
"""
from __future__ import annotations

import sys
from collections import Counter

from openpyxl import load_workbook

GRAIN = {
    "Results": ["Result ID"],
    "Core Flood": ["Result ID"],
    "Conditions": ["Experiment ID"],
    "XRD": ["Experiment ID", "Day"],
    "Rock XRD": ["Sample ID", "Analysis date", "Laboratory", "Analyst"],
    "Notes": ["Note ID"],
    "Experiments": ["Experiment ID"],
}
RISKY = ("=", "+", "-", "@")


def audit(path: str) -> None:
    print(f"\n=== {path}")
    wb = load_workbook(path)  # not data_only: formula cells keep data_type 'f'
    summary = {}
    if "Summary" in wb.sheetnames:
        for row in wb["Summary"].iter_rows(min_row=2, values_only=True):
            summary[row[0]] = row[1]
        for k, v in summary.items():
            if not str(k).startswith("Rows:") and k != "Experiment IDs":
                print(f"  summary {k!r}: {str(v)[:200]!r}")
    print(f"  sheets: {wb.sheetnames}")

    exp_ids: set[str] = set()
    if "Experiments" in wb.sheetnames:
        exp_ids = {r[0] for r in wb["Experiments"].iter_rows(min_row=2, values_only=True)
                   if r[0] is not None}
    elif "Experiment IDs" in summary:
        exp_ids = {s.strip() for s in str(summary["Experiment IDs"]).split(",")}
    print(f"  experiment IDs known: {len(exp_ids)}")

    per_tab_ids: dict[str, set] = {}
    for ws in wb.worksheets:
        if ws.title == "Summary":
            continue
        header = [c.value for c in ws[1]]
        rows = list(ws.iter_rows(min_row=2))
        data = [r for r in rows if any(c.value is not None for c in r)]
        blank_inside = len(rows) - len(data)
        declared = summary.get(f"Rows: {ws.title}")
        print(f"\n  [{ws.title}] data rows={len(data)} summary={declared} "
              f"max_row={ws.max_row} blank rows={blank_inside} cols={len(header)}"
              + ("  <-- MISMATCH" if declared is not None and declared != len(data) else ""))

        col = {h: i for i, h in enumerate(header)}
        if ws.title in GRAIN and all(g in col for g in GRAIN[ws.title]):
            keys = Counter(tuple(r[col[g]].value for g in GRAIN[ws.title]) for r in data)
            dups = {k: n for k, n in keys.items() if n > 1}
            print(f"    duplicate grain keys {GRAIN[ws.title]}: {len(dups)}"
                  + (f" e.g. {list(dups.items())[:5]}" if dups else ""))
        if "Experiment ID" in col:
            ids = {r[col["Experiment ID"]].value for r in data}
            per_tab_ids[ws.title] = ids
            orphans = ids - exp_ids if exp_ids else set()
            if orphans:
                print(f"    IDs not in experiment set: {sorted(orphans)[:10]} ({len(orphans)})")

        risky, formulas, long_cells = [], [], []
        for r in data:
            for c in r:
                if c.data_type == "f":
                    formulas.append((c.coordinate, str(c.value)[:60]))
                elif isinstance(c.value, str):
                    if c.value.startswith(RISKY):
                        risky.append((c.coordinate, c.value[:60]))
                    if len(c.value) > 32767:
                        long_cells.append((c.coordinate, len(c.value)))
        if formulas:
            print(f"    FORMULA cells: {len(formulas)} e.g. {formulas[:5]}")
        if risky:
            print(f"    text cells starting with = + - @: {len(risky)} e.g. {risky[:5]}")
        if long_cells:
            print(f"    cells > 32767 chars: {long_cells}")
        empty = [h for i, h in enumerate(header)
                 if all(r[i].value is None for r in data)]
        if empty:
            print(f"    entirely empty columns ({len(empty)}): {empty}")
        if ws.title in ("Results", "Conditions", "XRD", "Notes") and data:
            first, last = data[0][0].value, data[-1][0].value
            print(f"    first row ID={first!r} last row ID={last!r}")

    for tab in ("Results", "Conditions"):
        if tab in per_tab_ids and exp_ids:
            missing = sorted(exp_ids - per_tab_ids[tab])
            print(f"\n  experiments with zero rows on {tab}: {len(missing)}"
                  + (f" e.g. {missing[:15]}" if missing else ""))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        audit(p)
