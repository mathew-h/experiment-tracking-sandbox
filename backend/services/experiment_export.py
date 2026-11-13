"""Export all (issue #141): one Excel workbook for an experiment's lineage.

The lineage is every experiment sharing the requested experiment's
base_experiment_id (the experiment alone when it has none): the root, its
sequential segments (CF_027, CF_027-2, ...) and their `_Text` side samples
(blanks, bypass), which are flagged is_variant.

Every value comes from the reporting views that Power BI also reads, so the
workbook and the report cannot disagree. Nothing is recomputed here except
is_variant on the Results tab, which uses the same rule as v_core_flood_samples
(a child whose ID is `<parent>_<Text>`).
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Callable

import structlog
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from backend.api.schemas.results import ICP_ELEMENTS
from backend.services.core_flood_service import is_core_flood
from backend.services.experiment_lookup import (
    find_experiment, is_variant, lowest_conditions_map, series_key,
)
from backend.services.replicate_collapse import timepoint_stem_expr
from backend.services.run_service import root_description
from backend.services.workdays import LAB_TZ
from database.experiment_id_parser import split_timepoint_token
from database.models.experiments import Experiment

log = structlog.get_logger(__name__)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_EPOCH = datetime.min.replace(tzinfo=LAB_TZ)


# The only size limit is the file format's: an Excel sheet holds 1,048,576
# rows including the header (issue #168). Measured on the 2026-11-06 dump,
# exporting every experiment takes ~3 s and its largest tab has ~5,700 rows.
EXCEL_MAX_ROWS: int = 1_048_576

# Text starting with one of these is a formula to Excel (openpyxl writes
# "=..." as one); such cells are written as text (issue #168, B6).
_FORMULA_CHARS = ("=", "+", "-", "@")


class ExportNotFound(Exception):
    """The requested experiment does not exist (maps to 404)."""


class ExportRejected(Exception):
    """The selection cannot be exported (maps to 422)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class Member:
    """One experiment of the exported lineage."""

    id: int
    experiment_id: str
    base_id: str
    experiment_type: str | None
    is_variant: bool
    status: str | None
    date: datetime | None
    description: str | None
    is_root: bool
    is_core_flood: bool


@dataclass(frozen=True)
class Lineage:
    base_id: str
    members: list[Member]

    @property
    def ids(self) -> list[str]:
        return [m.experiment_id for m in self.members]

    @property
    def fks(self) -> list[int]:
        return [m.id for m in self.members]


# A column is (source key in the row dict, header). Units go in the header.
Column = tuple[str, str]

RESULT_COLUMNS: list[Column] = [
    ("experiment_id", "Experiment ID"),
    ("is_variant", "is_variant"),
    ("result_id", "Result ID"),
    ("sample_tube_number", "Tube number"),
    ("time_post_reaction_days", "Day"),
    ("time_post_reaction_bucket_days", "Day bucket"),
    ("cumulative_time_post_reaction_days", "Cumulative day"),
    ("scalar_measurement_date", "Sample date"),
    ("final_ph", "pH"),
    ("gross_ammonium_concentration_mM", "NH4+ gross (mM)"),
    ("background_ammonium_concentration_mM", "NH4+ background (mM)"),
    ("net_ammonium_concentration", "NH4+ net (mM)"),
    ("ammonium_quant_method", "NH4+ quant method"),
    ("grams_per_ton_yield", "NH3 yield (g/t)"),
    ("final_nitrate_concentration_mM", "Nitrate (mM)"),
    ("ferrous_iron_yield", "Fe2+ yield (%)"),
    ("ferrous_iron_yield_h2_pct", "Fe2+ yield, H2-derived (%)"),
    ("cumulative_ferrous_iron_yield_h2_pct", "Cumulative Fe2+ yield, H2-derived (%)"),
    ("ferrous_iron_yield_nh3_pct", "Fe2+ yield, NH3-derived (%)"),
    ("final_dissolved_oxygen_mg_L", "Dissolved O2 (mg/L)"),
    ("final_conductivity_mS_cm", "Conductivity (mS/cm)"),
    ("final_alkalinity_mg_L", "Alkalinity (mg/L)"),
    ("co2_partial_pressure_MPa", "CO2 partial pressure (MPa)"),
    ("sampling_volume_mL", "Sampling volume (mL)"),
    ("nmr_run_date", "NMR run date"),
    ("h2_concentration", "H2 (ppm)"),
    ("gas_sampling_volume_ml", "Gas sampling volume (mL)"),
    ("gas_sampling_pressure_MPa", "Gas sampling pressure (MPa)"),
    ("h2_micromoles", "H2 (µmol)"),
    ("h2_mass_ug", "H2 mass (µg)"),
    ("h2_grams_per_ton_yield", "H2 yield (g/t)"),
    ("gc_run_date", "GC run date"),
    ("icp_dilution_factor", "ICP dilution factor"),
    ("icp_instrument_used", "ICP instrument"),
    ("icp_raw_label", "ICP label"),
    ("icp_sample_date", "ICP sample date"),
    ("icp_run_date", "ICP run date"),
    # ICP element columns are inserted here (only elements with a reading).
    ("modification_note", "Modification note"),
]
_ICP_INSERT_BEFORE = "modification_note"

CORE_FLOOD_COLUMNS: list[Column] = [
    ("experiment_id", "Experiment ID"),
    ("is_variant", "is_variant"),
    ("result_id", "Result ID"),
    ("time_post_reaction_days", "Day"),
    ("cumulative_time_post_reaction_days", "Cumulative day"),
    ("sample_date", "Sample date"),
    ("gc_run_date", "GC run date"),
    ("sample_tube_number", "Tube number"),
    ("flow_rate_mL_min", "Flow (mL/min)"),
    ("is_hold_interval", "Hold interval"),
    ("nitrogen_flow_rate_mL_min", "N2 flow (mL/min)"),
    ("permeability_flow_rate_mL_min", "Permeability test flow (mL/min)"),
    ("inlet_pressure_psi", "Inlet pressure (psi)"),
    ("outlet_pressure_psi", "Outlet pressure (psi)"),
    ("sampling_volume_mL", "Sampling volume (mL)"),
    ("h2_concentration", "H2 (ppm)"),
    ("gas_sampling_volume_ml", "Gas sampling volume (mL)"),
    ("gas_sampling_pressure_MPa", "Gas sampling pressure (MPa)"),
    ("h2_micromoles", "H2 (µmol)"),
    ("h2_mass_ug", "H2 mass (µg)"),
    ("h2_grams_per_ton_yield", "H2 yield (g/t)"),
    ("final_ph", "pH"),
    ("final_conductivity_mS_cm", "Conductivity (mS/cm)"),
    ("pore_volume_mL", "Pore volume (mL)"),
    ("interval_days", "Interval (days)"),
    ("cumulative_liquid_volume_mL", "Cumulative liquid volume (mL)"),
    ("cumulative_pore_volumes", "Cumulative pore volumes"),
    ("cumulative_h2_grams_per_ton", "Cumulative H2 (g/t)"),
    ("h2_grams_per_ton_per_day", "H2 rate (g/t/day)"),
]

CONDITION_COLUMNS: list[Column] = [
    ("experiment_id", "Experiment ID"),
    ("experiment_type", "Experiment type"),
    ("reactor_number", "Reactor number"),
    ("feedstock", "Feedstock"),
    ("temperature_c", "Temperature (°C)"),
    ("particle_size", "Particle size"),
    ("initial_ph", "Initial pH"),
    ("rock_mass_g", "Rock mass (g)"),
    ("water_volume_mL", "Water volume (mL)"),
    ("serum_vial_size_mL", "Serum vial size (mL)"),
    ("water_to_rock_ratio", "Water to rock ratio"),
    ("stir_speed_rpm", "Stir speed (rpm)"),
    ("room_temp_pressure_psi", "Room-temperature pressure (psi)"),
    ("rxn_temp_pressure_psi", "Reaction-temperature pressure (psi)"),
    ("co2_partial_pressure_MPa", "CO2 partial pressure (MPa)"),
    ("confining_pressure", "Confining pressure"),
    ("pore_pressure", "Pore pressure"),
    ("flow_rate", "Flow rate"),
    ("initial_conductivity_mS_cm", "Initial conductivity (mS/cm)"),
    ("initial_nitrate_concentration", "Initial nitrate (mM)"),
    ("initial_dissolved_oxygen", "Initial dissolved O2 (ppm)"),
    ("initial_alkalinity", "Initial alkalinity"),
    ("core_height_cm", "Core height (cm)"),
    ("core_width_cm", "Core width (cm)"),
    ("core_volume_cm3", "Core volume (cm3)"),
    ("pore_volume_mL", "Pore volume (mL)"),
    ("total_ferrous_iron_g", "Total Fe2+ (g)"),
    ("total_ferrous_iron", "Total Fe2+ initial (g)"),
]

ADDITIVE_COLUMNS: list[Column] = [
    ("experiment_id", "Experiment ID"),
    ("compound_name", "Compound"),
    ("formula", "Formula"),
    ("amount", "Amount"),
    ("unit", "Unit"),
    ("addition_order", "Addition order"),
    ("addition_method", "Addition method"),
    ("purity", "Purity (%)"),
    ("mass_in_grams", "Mass (g)"),
    ("moles_added", "Moles added (mol)"),
    ("final_concentration", "Final concentration"),
    ("concentration_units", "Concentration units"),
    ("elemental_metal_mass", "Elemental metal mass (g)"),
    ("catalyst_percentage", "Catalyst (% of rock mass)"),
    ("catalyst_ppm", "Catalyst (ppm)"),
]

XRD_COLUMNS: list[Column] = [
    ("experiment_id", "Experiment ID"),
    ("is_variant", "is_variant"),
    ("time_post_reaction_days", "Day"),
    ("measurement_date", "Measurement date"),
    ("rwp", "Rwp"),
    # One "<mineral> (%)" column per mineral in the export is appended.
]

ROCK_XRD_COLUMNS: list[Column] = [
    ("sample_id", "Sample ID"),
    ("used_by", "Used by"),
    ("analysis_date", "Analysis date"),
    ("laboratory", "Laboratory"),
    ("analyst", "Analyst"),
    # One "<mineral> (%)" column per mineral in the export is appended.
]

# Row-dict key prefix for mineral columns, so a mineral can never collide with
# a fixed column key.
_MINERAL_KEY = "mineral:"

NOTE_COLUMNS: list[Column] = [
    ("experiment_id", "Experiment ID"),
    ("note_id", "Note ID"),
    ("note_type", "Type"),
    ("event_date", "Event date"),
    ("result_id", "Result ID"),
    ("note_text", "Text"),
    ("created_by", "Author"),
    ("created_at", "Created at"),
    ("needs_review", "Needs review"),
]


# ---------------------------------------------------------------------------
# Lineage
# ---------------------------------------------------------------------------

def _load_members(db: Session, exps: list[Experiment]) -> list[Member]:
    """Members for `exps` (one conditions query). Unsorted; see _series_order."""
    conditions = lowest_conditions_map(db, [e.id for e in exps])

    members: list[Member] = []
    for e in exps:
        parent = e.parent
        cond = conditions.get(e.id)
        members.append(Member(
            id=e.id,
            experiment_id=e.experiment_id,
            base_id=series_key(e),
            experiment_type=cond.experiment_type if cond is not None else None,
            is_variant=is_variant(e),
            status=e.status.value if e.status is not None else None,
            date=e.date,
            description=e.description,
            is_root=parent is None,
            is_core_flood=is_core_flood(cond),
        ))
    return members


def _series_order(members: list[Member]) -> list[Member]:
    """Series by base ID, then experiment date (undated last), then ID stem and
    -t day (numeric, so -t3 precedes -t20), so a side sample such as
    CF_027-2_Bypass1 follows its parent segment when they share a start date."""
    def key(m: Member):
        stem, tp = split_timepoint_token(m.experiment_id)
        # Vials share the text key "<stem>-t" so only their day orders them;
        # every other ID keeps its plain text order (X-2 before X-t1).
        text_key = m.experiment_id if tp is None else f"{stem}-t"
        return (m.base_id, m.date is None, m.date or _EPOCH, text_key,
                tp is not None, tp or 0, m.experiment_id)
    return sorted(members, key=key)


def _load_experiments(db: Session, clause) -> list[Experiment]:
    return list(db.execute(
        select(Experiment)
        .options(selectinload(Experiment.parent),
                 selectinload(Experiment.description_note))
        .where(clause)
    ).scalars())


def resolve_lineage(db: Session, experiment_id: str) -> Lineage:
    """The requested experiment's lineage, ordered as segments."""
    exp = find_experiment(db, experiment_id)
    if exp is None:
        raise ExportNotFound(experiment_id)

    if exp.base_experiment_id:
        exps = _load_experiments(
            db, (Experiment.base_experiment_id == exp.base_experiment_id)
            | (Experiment.id == exp.id))
    else:
        exps = _load_experiments(db, Experiment.id == exp.id)
    members = _series_order(_load_members(db, exps))
    return Lineage(base_id=series_key(exp),
                   members=members)


def resolve_selection(db: Session, experiment_ids: list[str],
                      include_series: bool) -> list[Member]:
    """Members for a picked list of experiment IDs.

    A pick expands to every vial of its timepoint stem (SERUM_001-t1 brings
    -t3, -t7); with include_series, to every experiment sharing the base ID of
    any of those.
    """
    picks = list(dict.fromkeys(experiment_ids))
    found = _load_experiments(db, Experiment.experiment_id.in_(picks))
    have = {e.experiment_id for e in found}
    missing = [i for i in picks if i not in have]
    if missing:
        raise ExportRejected("Unknown experiment IDs: " + ", ".join(missing))

    stems = {split_timepoint_token(e.experiment_id)[0] for e in found}
    exps = {e.id: e for e in _load_experiments(
        db, timepoint_stem_expr(Experiment).in_(stems))}
    exps.update({e.id: e for e in found})
    if include_series:
        bases = {e.base_experiment_id for e in exps.values()
                 if e.base_experiment_id}
        if bases:
            exps.update({e.id: e for e in _load_experiments(
                db, Experiment.base_experiment_id.in_(bases))})
    return _series_order(_load_members(db, list(exps.values())))


# ---------------------------------------------------------------------------
# Tab data (each a list of row dicts keyed by view column)
# ---------------------------------------------------------------------------

def _rows(db: Session, sql: str, params: dict) -> list[dict]:
    return [dict(r) for r in db.execute(text(sql), params).mappings()]


def _by_result(rows: list[dict]) -> dict[int, dict]:
    return {r["result_id"]: r for r in rows}


def results_rows(db: Session, members: list[Member]) -> tuple[list[dict], list[str]]:
    """Results rows and the ICP elements (ICP_ELEMENTS order) with a reading."""
    params = {"fks": [m.id for m in members]}
    scalar = _rows(db, "SELECT * FROM v_results_scalar WHERE experiment_fk = ANY(:fks)",
                   params)
    h2 = _by_result(_rows(
        db, "SELECT * FROM v_results_h2 WHERE experiment_fk = ANY(:fks)", params))
    icp = _by_result(_rows(
        db, "SELECT * FROM v_results_icp WHERE experiment_fk = ANY(:fks)", params))
    tp = _by_result(_rows(
        db, "SELECT t.* FROM v_dim_timepoints t JOIN experimental_results er"
            " ON er.id = t.result_id WHERE er.experiment_fk = ANY(:fks)", params))

    order = {m.id: i for i, m in enumerate(members)}
    variant = {m.id: m.is_variant for m in members}
    out: list[dict] = []
    for s in scalar:
        rid = s["result_id"]
        # Later sources never overwrite a key already present (the shared
        # experiment_id / time columns are identical across the views).
        row = dict(s)
        for extra in (h2.get(rid), icp.get(rid), tp.get(rid)):
            for k, v in (extra or {}).items():
                row.setdefault(k, v)
        row["is_variant"] = variant[s["experiment_fk"]]
        out.append(row)
    out.sort(key=lambda r: (
        order[r["experiment_fk"]],
        r["cumulative_time_post_reaction_days"] is None,
        r["cumulative_time_post_reaction_days"] or 0,
        r["result_id"],
    ))
    elements = [e for e in ICP_ELEMENTS
                if any(r.get(f"{e}_ppm") is not None for r in out)]
    return out, elements


def core_flood_rows(db: Session, members: list[Member]) -> list[dict]:
    """Series in member order; within a series, segments before side samples,
    then cumulative day (issue #168, B5: the view order alone interleaved
    the series of a multi-series selection)."""
    rows = _rows(
        db,
        "SELECT * FROM v_core_flood_samples WHERE experiment_fk = ANY(:fks)"
        " ORDER BY is_variant, cumulative_time_post_reaction_days NULLS LAST,"
        " result_id",
        {"fks": [m.id for m in members]})
    series = {}
    for m in members:
        series.setdefault(m.base_id, len(series))
    series_of = {m.id: series[m.base_id] for m in members}
    # Stable sort: keeps the view's order within each series.
    return sorted(rows, key=lambda r: series_of[r["experiment_fk"]])


def _ordered_by_member(members: list[Member], rows: list[dict],
                       key: Callable[[dict], Any]) -> list[dict]:
    order = {m.experiment_id: i for i, m in enumerate(members)}
    return sorted(rows, key=lambda r: (order[r["experiment_id"]], key(r)))


def _ids(members: list[Member]) -> list[str]:
    return [m.experiment_id for m in members]


def condition_rows(db: Session, members: list[Member]) -> list[dict]:
    rows = _rows(db, "SELECT * FROM v_experiment_conditions"
                     " WHERE experiment_id = ANY(:ids)", {"ids": _ids(members)})
    return _ordered_by_member(members, rows, lambda r: 0)


def additive_rows(db: Session, members: list[Member]) -> list[dict]:
    rows = _rows(db, "SELECT * FROM v_chemical_additives"
                     " WHERE experiment_id = ANY(:ids)", {"ids": _ids(members)})
    return _ordered_by_member(members, rows, lambda r: (
        r["addition_order"] is None, r["addition_order"] or 0, r["compound_name"]))


def _pivot_minerals(long_rows: list[dict], key: Callable[[dict], tuple],
                    fixed: Callable[[dict], dict]
                    ) -> tuple[list[dict], list[str]]:
    """Long view rows (one per mineral) as one wide row per `key`.

    Mineral names are kept exactly as stored (no case folding), as everywhere
    else in the export. Returns the rows in first-seen key order and the
    minerals present, alphabetical (case-insensitive).
    """
    wide: dict[tuple, dict] = {}
    for r in long_rows:
        row = wide.setdefault(key(r), fixed(r))
        row[_MINERAL_KEY + r["mineral_name"]] = r["amount_pct"]
    minerals = sorted({r["mineral_name"] for r in long_rows},
                      key=lambda m: (m.casefold(), m))
    return list(wide.values()), minerals


def _mineral_columns(minerals: list[str]) -> list[Column]:
    return [(_MINERAL_KEY + m, f"{m} (%)") for m in minerals]


def xrd_rows(db: Session, members: list[Member]) -> tuple[list[dict], list[str]]:
    """Post-reaction XRD (Aeris time series): one row per experiment and day."""
    long_rows = _rows(db, "SELECT * FROM v_experiment_xrd"
                          " WHERE experiment_id = ANY(:ids)", {"ids": _ids(members)})
    variant = {m.experiment_id: m.is_variant for m in members}
    # rwp and measurement_date are per scan, so every mineral row of one
    # (experiment, day) carries the same values; the first one is kept.
    rows, minerals = _pivot_minerals(
        long_rows,
        key=lambda r: (r["experiment_id"], r["time_post_reaction_days"]),
        fixed=lambda r: {
            "experiment_id": r["experiment_id"],
            "is_variant": variant[r["experiment_id"]],
            "time_post_reaction_days": r["time_post_reaction_days"],
            "measurement_date": r["measurement_date"],
            "rwp": r["rwp"],
        })
    rows = _ordered_by_member(members, rows, lambda r: (
        r["time_post_reaction_days"] is None, r["time_post_reaction_days"] or 0))
    return rows, minerals


def rock_xrd_rows(db: Session, members: list[Member]
                  ) -> tuple[list[dict], list[str]]:
    """Starting-rock XRD: one row per analysis of a sample the members use.

    `Used by` lists the exported members with that sample ID, in member order.
    """
    sample_of = {r["experiment_id"]: r["sample_id"] for r in _rows(
        db, "SELECT experiment_id, sample_id FROM v_experiments"
            " WHERE experiment_id = ANY(:ids) AND sample_id IS NOT NULL",
        {"ids": _ids(members)})}
    used_by: dict[str, list[str]] = {}
    for m in members:
        if m.experiment_id in sample_of:
            used_by.setdefault(sample_of[m.experiment_id], []).append(m.experiment_id)
    if not used_by:
        return [], []

    long_rows = _rows(db, "SELECT * FROM v_sample_xrd WHERE sample_id = ANY(:sids)",
                      {"sids": list(used_by)})
    rows, minerals = _pivot_minerals(
        long_rows,
        key=lambda r: (r["sample_id"], r["analysis_date"], r["laboratory"],
                       r["analyst"]),
        fixed=lambda r: {
            "sample_id": r["sample_id"],
            "used_by": ", ".join(used_by[r["sample_id"]]),
            "analysis_date": r["analysis_date"],
            "laboratory": r["laboratory"],
            "analyst": r["analyst"],
        })
    # Samples in the order their first user appears, then by analysis date.
    first_use = {sid: i for i, sid in enumerate(used_by)}
    rows.sort(key=lambda r: (first_use[r["sample_id"]], r["analysis_date"] is None,
                             r["analysis_date"] or _EPOCH))
    return rows, minerals


def note_rows(db: Session, members: list[Member]) -> list[dict]:
    rows = _rows(db, "SELECT * FROM v_notes WHERE experiment_id = ANY(:ids)",
                 {"ids": _ids(members)})
    return _ordered_by_member(members, rows, lambda r: (
        r["created_at"] is None, r["created_at"] or _EPOCH, r["note_id"]))


# ---------------------------------------------------------------------------
# Workbook
# ---------------------------------------------------------------------------

_DATETIME_FMT = "yyyy-mm-dd hh:mm"
_DATE_FMT = "yyyy-mm-dd"
_BOLD = Font(bold=True)


def lab_now() -> datetime:
    return datetime.now(LAB_TZ)


def _cell(value: Any) -> Any:
    """A view value as an openpyxl cell value (Excel dates are lab-local, naive)."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(LAB_TZ).replace(tzinfo=None)
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    return value


def _write_tab(wb: Workbook, title: str, columns: list[Column],
               rows: list[dict]) -> None:
    ws = wb.create_sheet(title)
    ws.append([header for _, header in columns])
    for c in ws[1]:
        c.font = _BOLD
    ws.freeze_panes = "A2"
    for r in rows:
        ws.append([_cell(r.get(key)) for key, _ in columns])

    for idx, (key, header) in enumerate(columns, start=1):
        cells = [ws.cell(row=i, column=idx) for i in range(2, len(rows) + 2)]
        dts = [c for c in cells if isinstance(c.value, datetime)]
        if dts:
            # A column whose every timestamp is lab-local midnight is a date column.
            date_only = all(c.value.time() == time.min for c in dts)
            for c in dts:
                c.number_format = _DATE_FMT if date_only else _DATETIME_FMT
        for c in cells:
            if isinstance(c.value, date) and not isinstance(c.value, datetime):
                c.number_format = _DATE_FMT
            elif isinstance(c.value, str) and c.value.startswith(_FORMULA_CHARS):
                # Text, never a formula; quotePrefix keeps Excel from
                # re-reading it as one when the cell is edited.
                c.data_type = "s"
                c.quotePrefix = True
        if dts:
            width = max(len(header), 16)
        else:
            width = max([len(header)] + [min(len(str(c.value)), 60)
                                         for c in cells if c.value is not None])
        ws.column_dimensions[get_column_letter(idx)].width = max(10, width + 2)


def _check_sheet_limits(tabs: list[tuple[str, list[Column], list[dict]]]) -> None:
    """Raise ExportRejected for the first tab that would not fit on a sheet."""
    limit = EXCEL_MAX_ROWS - 1  # the header takes one row
    for title, _columns, rows in tabs:
        if len(rows) > limit:
            raise ExportRejected(
                f"Export too large: the {title} tab has {len(rows):,} rows and "
                f"an Excel sheet holds at most {limit:,}. Narrow the selection.")


def _results_columns(elements: list[str]) -> list[Column]:
    cut = [k for k, _ in RESULT_COLUMNS].index(_ICP_INSERT_BEFORE)
    icp = [(f"{e}_ppm", f"{e.capitalize()} (ppm)") for e in elements]
    return RESULT_COLUMNS[:cut] + icp + RESULT_COLUMNS[cut:]


def _root_description(lineage: Lineage) -> str | None:
    return root_description(lineage.members, is_root=lambda m: m.is_root and not m.is_variant)


def _data_tabs(db: Session, members: list[Member]
               ) -> list[tuple[str, list[Column], list[dict]]]:
    results, elements = results_rows(db, members)
    tabs: list[tuple[str, list[Column], list[dict]]] = [
        ("Results", _results_columns(elements), results)]
    if any(m.is_core_flood for m in members):
        tabs.append(("Core Flood", CORE_FLOOD_COLUMNS, core_flood_rows(db, members)))
    # XRD tabs only when the export has XRD of that kind.
    xrd, xrd_minerals = xrd_rows(db, members)
    if xrd:
        tabs.append(("XRD", XRD_COLUMNS + _mineral_columns(xrd_minerals), xrd))
    rock, rock_minerals = rock_xrd_rows(db, members)
    if rock:
        tabs.append(("Rock XRD", ROCK_XRD_COLUMNS + _mineral_columns(rock_minerals),
                     rock))
    tabs += [
        ("Conditions", CONDITION_COLUMNS, condition_rows(db, members)),
        ("Additives", ADDITIVE_COLUMNS, additive_rows(db, members)),
        ("Notes", NOTE_COLUMNS, note_rows(db, members)),
    ]
    return tabs


def build_workbook(db: Session, experiment_id: str,
                   exported_by: str | None = None) -> tuple[str, bytes]:
    """(filename, xlsx bytes) for the lineage of `experiment_id`.

    Raises ExportNotFound when the experiment does not exist, ExportRejected
    when a tab would exceed Excel's sheet row limit.
    """
    lineage = resolve_lineage(db, experiment_id)
    now = lab_now()

    tabs = _data_tabs(db, lineage.members)
    _check_sheet_limits(tabs)

    wb = Workbook()
    wb.remove(wb.active)
    for title, columns, rows in tabs:
        _write_tab(wb, title, columns, rows)

    summary: list[dict] = [
        # The requested ID is deliberately absent: any segment's ID must give
        # the same workbook.
        {"key": "Base ID", "value": lineage.base_id},
        {"key": "Experiment IDs", "value": ", ".join(lineage.ids)},
        {"key": "Experiment count", "value": len(lineage.members)},
        {"key": "Side samples (is_variant)", "value": ", ".join(
            m.experiment_id for m in lineage.members if m.is_variant) or None},
        {"key": "Description", "value": _root_description(lineage)},
        {"key": "Status", "value": "; ".join(
            f"{m.experiment_id}: {m.status or '—'}" for m in lineage.members)},
        {"key": "Exported at", "value": now},
        {"key": "Exported by", "value": exported_by},
    ] + [{"key": f"Rows: {title}", "value": len(rows)} for title, _, rows in tabs]
    _write_tab(wb, "Summary", [("key", "Field"), ("value", "Value")], summary)

    buf = io.BytesIO()
    wb.save(buf)
    filename = f"{lineage.base_id}_export_{now.date().isoformat()}.xlsx"
    log.info("experiment_export_built", base_id=lineage.base_id,
             experiments=len(lineage.members),
             rows={title: len(rows) for title, _, rows in tabs})
    return filename, buf.getvalue()


EXPERIMENT_COLUMNS: list[Column] = [
    ("experiment_id", "Experiment ID"),
    ("base_id", "Base ID"),
    ("is_variant", "is_variant"),
    ("status", "Status"),
    ("experiment_type", "Experiment type"),
    ("date", "Start date"),  # issue #168: was "Date"
    ("researcher", "Researcher"),
    ("sample_id", "Sample ID"),
    ("reactor_number", "Reactor number"),
    ("description", "Description"),
]


def build_selection_workbook(db: Session, experiment_ids: list[str],
                             include_series: bool,
                             exported_by: str | None = None) -> tuple[str, bytes]:
    """(filename, xlsx bytes) for a picked list of experiments.

    Raises ExportRejected for unknown IDs, or when a tab would exceed Excel's
    sheet row limit.
    """
    members = resolve_selection(db, experiment_ids, include_series)
    now = lab_now()

    view = {r["experiment_id"]: r for r in _rows(
        db, "SELECT * FROM v_experiments WHERE experiment_id = ANY(:ids)",
        {"ids": [m.experiment_id for m in members]})}
    experiments = [
        {**view.get(m.experiment_id, {}), "base_id": m.base_id,
         "is_variant": m.is_variant}
        for m in members]
    tabs = [("Experiments", EXPERIMENT_COLUMNS, experiments)
            ] + _data_tabs(db, members)
    _check_sheet_limits(tabs)

    wb = Workbook()
    wb.remove(wb.active)
    for title, columns, rows in tabs:
        _write_tab(wb, title, columns, rows)

    base_ids = list(dict.fromkeys(m.base_id for m in members))
    summary: list[dict] = [
        {"key": "Experiment count", "value": len(members)},
        {"key": "Series count", "value": len(base_ids)},
        {"key": "Base IDs", "value": ", ".join(base_ids)},
        {"key": "Include whole series", "value": "Yes" if include_series else "No"},
        {"key": "Side samples (is_variant)", "value": ", ".join(
            m.experiment_id for m in members if m.is_variant) or None},
        {"key": "Exported at", "value": now},
        {"key": "Exported by", "value": exported_by},
    ] + [{"key": f"Rows: {title}", "value": len(rows)} for title, _, rows in tabs]
    _write_tab(wb, "Summary", [("key", "Field"), ("value", "Value")], summary)

    buf = io.BytesIO()
    wb.save(buf)
    filename = f"data_export_{now.date().isoformat()}.xlsx"
    log.info("experiment_export_selection_built", experiments=len(members),
             series=len(base_ids), include_series=include_series,
             rows={title: len(rows) for title, _, rows in tabs})
    return filename, buf.getvalue()
