"""Issue #168 Part 2 step 1: time and memory for build_selection_workbook.

Runs one scenario per process (so peak memory is per scenario) against the
scratch experiments_audit168 database. The 500-experiment cap is lifted.

Usage (repo root):
  PYTHONPATH=. .venv/Scripts/python docs/working/export_audit/measure.py <scenario>
  scenario: page_off | page_on | all
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import io
import sys
import time
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent))
from auditdb import engine  # noqa: E402

from backend.services import experiment_export as ex  # noqa: E402
from database.models.experiments import Experiment  # noqa: E402


class _PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def _mem() -> tuple[float, float]:
    """(working set, peak working set) in MB."""
    pmc = _PMC()
    pmc.cb = ctypes.sizeof(_PMC)
    k32 = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    k32.GetCurrentProcess.restype = wt.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_PMC), wt.DWORD]
    psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
    return pmc.WorkingSetSize / 2**20, pmc.PeakWorkingSetSize / 2**20


def main(scenario: str) -> None:
    ex.EXPORT_MAX_EXPERIMENTS = 10**9
    with Session(engine) as db:
        q = select(Experiment.experiment_id)
        if scenario.startswith("page"):
            # The Data Export page: group_replicates=false, newest first, 500.
            q = q.order_by(Experiment.experiment_number.desc()).limit(500)
        picks = list(db.execute(q).scalars())
        include = scenario != "page_off"

        ws0, _ = _mem()
        t0 = time.perf_counter()
        members = ex.resolve_selection(db, picks, include)
        t1 = time.perf_counter()
        _name, data = ex.build_selection_workbook(db, picks, include)
        t2 = time.perf_counter()
        _ws, peak = _mem()

    wb = load_workbook(io.BytesIO(data), read_only=True)
    summary = {r[0]: r[1] for r in wb["Summary"].iter_rows(min_row=2, values_only=True)}
    rows = {k[6:]: v for k, v in summary.items() if str(k).startswith("Rows: ")}
    print(f"scenario={scenario} picks={len(picks)} include_series={include} "
          f"expanded={len(members)}")
    print(f"  resolve {t1 - t0:.2f}s; build_selection_workbook {t2 - t1:.2f}s "
          f"(includes its own resolve)")
    print(f"  file {len(data) / 2**20:.2f} MB; "
          f"process working set before {ws0:.0f} MB, peak {peak:.0f} MB")
    print(f"  rows {rows}")


if __name__ == "__main__":
    main(sys.argv[1])
