import logging
from sqlalchemy import event, text
from sqlalchemy.orm import Session, attributes
from .models import (
    ExternalAnalysis, SampleInfo, ChemicalAdditive, ElementalAnalysis, Experiment,
    ExperimentalConditions,
)
from .database import engine
from .lineage_utils import update_experiment_lineage, update_orphaned_derivations
from database.experiment_id_parser import TIMEPOINT_TOKEN_SQL_PATTERN

logger = logging.getLogger(__name__)

def update_sample_characterized_status(session: Session, sample_id: str):
    """
    Updates the 'characterized' status of a SampleInfo record based on
    the existence of XRD analyses or titration (elemental) data. This should be called
    within a 'before_flush' event.
    """
    if not sample_id:
        return

    # Combine all known instances in the session for this sample_id
    all_instances = (
        session.query(ExternalAnalysis)
        .filter(ExternalAnalysis.sample_id == sample_id)
        .all()
    )

    # Add newly created instances that are not yet in the query result
    for obj in session.new:
        if isinstance(obj, ExternalAnalysis) and obj.sample_id == sample_id:
            if obj not in all_instances:
                all_instances.append(obj)

    # Filter out instances marked for deletion
    final_instances = [
        instance for instance in all_instances if instance not in session.deleted
    ]

    # XRD via ExternalAnalysis entries
    has_xrd = any(instance.analysis_type == 'XRD' for instance in final_instances)

    # Titration/elemental data via ElementalAnalysis normalized table
    # Start with DB state
    titration_instances = (
        session.query(ElementalAnalysis)
        .filter(ElementalAnalysis.sample_id == sample_id)
        .all()
    )
    # Remove any that are being deleted this flush
    titration_final = [ea for ea in titration_instances if ea not in session.deleted]
    # Include any new ones not yet persisted
    for obj in session.new:
        if isinstance(obj, ElementalAnalysis) and obj.sample_id == sample_id:
            if obj not in titration_final:
                titration_final.append(obj)

    has_titration = len(titration_final) > 0

    is_characterized = has_xrd or has_titration

    sample_info = session.query(SampleInfo).filter(SampleInfo.sample_id == sample_id).first()

    if sample_info and sample_info.characterized != is_characterized:
        sample_info.characterized = is_characterized

@event.listens_for(Session, 'before_flush')
def before_flush_handler(session, flush_context, instances):
    """
    Listen for changes before a flush and update characterized status.
    """
    samples_to_update = set()

    # Collect sample_ids from new, modified, and deleted ExternalAnalysis and ElementalAnalysis objects
    for obj in session.new.union(session.dirty):
        if isinstance(obj, ExternalAnalysis):
            samples_to_update.add(obj.sample_id)
            # If sample_id was changed, also update the old sample
            history = attributes.get_history(obj, 'sample_id')
            if history.has_changes() and history.deleted:
                samples_to_update.add(history.deleted[0])
        if isinstance(obj, ElementalAnalysis):
            samples_to_update.add(obj.sample_id)
            history = attributes.get_history(obj, 'sample_id')
            if history.has_changes() and history.deleted:
                samples_to_update.add(history.deleted[0])

    for obj in session.deleted:
        if isinstance(obj, ExternalAnalysis):
            samples_to_update.add(obj.sample_id)
        if isinstance(obj, ElementalAnalysis):
            samples_to_update.add(obj.sample_id)

    # Process all collected sample_ids
    for sample_id in samples_to_update:
        if sample_id:
            update_sample_characterized_status(session, sample_id)

# ---------------------------------------------------------------------------
# Reporting views for Power BI and direct SQL access.
# All views are dropped and recreated at import time so their definitions
# stay in sync with the current schema.  Failures are silently ignored so
# a missing DB at startup does not block the application.
# ---------------------------------------------------------------------------

_VIEWS = [
    # ------------------------------------------------------------------
    # v_experiments
    # One row per experiment.  Includes key setup fields pulled from
    # experimental_conditions and the note typed 'description'.
    #
    # Correctness fix (issue #118 PR3), not a refactor: this used to take the
    # first note by created_at. created_at is the transaction timestamp, so
    # every note a bulk upload inserted in one transaction shared it and the
    # LIMIT 1 was arbitrary; the app meanwhile took min(id). On the 2026-09-04
    # production mirror the two disagreed on 16 experiments (e.g. Power BI
    # showed "ICP Analysis - SERUM_JW_051-3_Day1_5x" where the app showed
    # "SERUM_JW_051 with EDTA and pH 11"). The partial unique index
    # uq_one_description_per_experiment guarantees at most one row here.
    # ------------------------------------------------------------------
    ("v_experiments", """
        CREATE VIEW v_experiments AS
        SELECT
            e.experiment_id,
            e.experiment_number,
            e.status,
            e.researcher,
            e.date,
            e.sample_id,
            e.base_experiment_id,
            ec.reactor_number,
            ec.rock_mass_g,
            ec."water_volume_mL",
            ec.initial_ph,
            ec.experiment_type,
            ec.feedstock,
            (SELECT n.note_text
             FROM experiment_notes n
             WHERE n.experiment_fk = e.id
               AND n.note_type = 'description') AS description
        FROM experiments e
        LEFT JOIN experimental_conditions ec ON ec.experiment_fk = e.id
    """),

    # ------------------------------------------------------------------
    # v_experiment_conditions
    # One row per experiment — full set of reactor / setup parameters.
    # Deprecated legacy fields (catalyst, buffer_system, surfactant, etc.)
    # are excluded; use v_chemical_additives for additive details.
    # ------------------------------------------------------------------
    ("v_experiment_conditions", """
        CREATE VIEW v_experiment_conditions AS
        SELECT
            e.experiment_id,
            ec.experiment_type,
            ec.temperature_c,
            ec.particle_size,
            ec.initial_ph,
            ec.rock_mass_g,
            ec."water_volume_mL",
            ec."serum_vial_size_mL",
            ec.water_to_rock_ratio,
            ec.reactor_number,
            ec.reactor_series,
            ec.reactor_slot,
            ec.feedstock,
            ec.stir_speed_rpm,
            ec.room_temp_pressure_psi,
            ec.rxn_temp_pressure_psi,
            ec."co2_partial_pressure_MPa",
            ec.confining_pressure,
            ec.pore_pressure,
            ec.flow_rate,
            ec."initial_conductivity_mS_cm",
            ec.initial_nitrate_concentration,
            ec.initial_dissolved_oxygen,
            ec.initial_alkalinity,
            ec.core_height_cm,
            ec.core_width_cm,
            ec.core_volume_cm3,
            ec."pore_volume_mL",
            ec.total_ferrous_iron_g,
            ec.total_ferrous_iron
        FROM experiments e
        JOIN experimental_conditions ec ON ec.experiment_fk = e.id
    """),

    # ------------------------------------------------------------------
    # v_chemical_additives
    # One row per additive per experiment (long format).
    # Join key to other views: experiment_id.
    # ------------------------------------------------------------------
    ("v_chemical_additives", """
        CREATE VIEW v_chemical_additives AS
        SELECT
            e.experiment_id,
            c.name        AS compound_name,
            c.formula,
            ca.amount,
            ca.unit,
            ca.addition_order,
            ca.addition_method,
            ca.purity,
            ca.mass_in_grams,
            ca.moles_added,
            ca.final_concentration,
            ca.concentration_units,
            ca.elemental_metal_mass,
            ca.catalyst_percentage,
            ca.catalyst_ppm
        FROM chemical_additives ca
        JOIN experimental_conditions ec ON ec.id = ca.experiment_id
        JOIN experiments e             ON e.id  = ec.experiment_fk
        JOIN compounds c               ON c.id  = ca.compound_id
    """),

    # ------------------------------------------------------------------
    # v_experiment_additives_summary
    # Convenience one-liner per experiment: all additives concatenated.
    # ------------------------------------------------------------------
    ("v_experiment_additives_summary", """
        CREATE VIEW v_experiment_additives_summary AS
        SELECT
            e.experiment_id,
            STRING_AGG(c.name || ' ' || ca.amount::TEXT || ' ' || ca.unit, '; ') AS additives_summary
        FROM chemical_additives ca
        JOIN experimental_conditions ec ON ec.id = ca.experiment_id
        JOIN experiments e              ON e.id  = ec.experiment_fk
        JOIN compounds c                ON c.id  = ca.compound_id
        GROUP BY e.experiment_id
    """),

    # ------------------------------------------------------------------
    # v_experiment_additive_names_summary
    # One row per experiment — compound names only, comma-separated and
    # alphabetically sorted.  additive_names is NULL for experiments with
    # no additives.  Use COALESCE(additive_names, '') at the consumer if
    # an empty string is preferred.
    # ------------------------------------------------------------------
    ("v_experiment_additive_names_summary", """
        CREATE VIEW v_experiment_additive_names_summary AS
        SELECT
            e.experiment_id,
            STRING_AGG(c.name, ', ' ORDER BY c.name) AS additive_names
        FROM experiments e
        LEFT JOIN experimental_conditions ec ON ec.experiment_fk = e.id
        LEFT JOIN chemical_additives ca      ON ca.experiment_id = ec.id
        LEFT JOIN compounds c                ON c.id = ca.compound_id
        GROUP BY e.experiment_id
    """),

    # ------------------------------------------------------------------
    # v_sample_info
    # One row per sample — core geological metadata.
    # ------------------------------------------------------------------
    ("v_sample_info", """
        CREATE VIEW v_sample_info AS
        SELECT
            sample_id,
            rock_classification,
            state,
            country,
            locality,
            latitude,
            longitude,
            description,
            characterized
        FROM sample_info
    """),

    # ------------------------------------------------------------------
    # v_sample_characterization
    # One row per external analysis per sample.
    # pxrf_reading_no is included as a link key only; element data lives
    # in v_pxrf_characterization.
    # ------------------------------------------------------------------
    ("v_sample_characterization", """
        CREATE VIEW v_sample_characterization AS
        SELECT
            ea.sample_id,
            ea.id          AS external_analysis_id,
            ea.analysis_type,
            ea.analysis_date,
            ea.laboratory,
            ea.analyst,
            ea.description,
            ea.magnetic_susceptibility,
            ea.pxrf_reading_no
        FROM external_analyses ea
        WHERE ea.sample_id IS NOT NULL
    """),

    # ------------------------------------------------------------------
    # v_pxrf_characterization
    # One row per pXRF reading per sample.
    # pxrf_reading_no on external_analyses may be comma-separated when
    # multiple readings were averaged; the LIKE join expands those cases
    # so each individual reading gets its own row.
    # ------------------------------------------------------------------
    ("v_pxrf_characterization", """
        CREATE VIEW v_pxrf_characterization AS
        SELECT
            ea.sample_id,
            pr.reading_no  AS pxrf_reading_no,
            ea.analysis_date,
            pr."Fe"        AS fe_ppm,
            pr."Mg"        AS mg_ppm,
            pr."Ni"        AS ni_ppm,
            pr."Cu"        AS cu_ppm,
            pr."Si"        AS si_ppm,
            pr."Co"        AS co_ppm,
            pr."Mo"        AS mo_ppm,
            pr."Al"        AS al_ppm,
            pr."Ca"        AS ca_ppm,
            pr."K"         AS k_ppm,
            pr."Au"        AS au_ppm,
            pr."Zn"        AS zn_ppm
        FROM external_analyses ea
        JOIN pxrf_readings pr ON (
            ea.pxrf_reading_no = pr.reading_no
            OR ea.pxrf_reading_no LIKE pr.reading_no || ',%'
            OR ea.pxrf_reading_no LIKE '%,' || pr.reading_no || ',%'
            OR ea.pxrf_reading_no LIKE '%,' || pr.reading_no
        )
        WHERE ea.sample_id IS NOT NULL
          AND ea.pxrf_reading_no IS NOT NULL
    """),

    # ------------------------------------------------------------------
    # v_sample_elemental_comp
    # One row per external analysis per sample, pivoted wide.
    # All 63 analyte symbols are represented as columns; values are NULL
    # when that analyte was not measured for a given analysis.
    # Column aliases use safe SQL identifiers (Fe2O3(T) → Fe2O3_T,
    # "Total 2" → Total_2) to avoid quoting issues in Power BI.
    # ------------------------------------------------------------------
    ("v_sample_elemental_comp", """
        CREATE VIEW v_sample_elemental_comp AS
        SELECT
            ea.sample_id,
            ea.id           AS external_analysis_id,
            ea.analysis_date,
            ea.laboratory,
            ea.analyst,
            MAX(CASE WHEN a.analyte_symbol = 'FeO'      THEN el.analyte_composition END) AS FeO,
            MAX(CASE WHEN a.analyte_symbol = 'SiO2'     THEN el.analyte_composition END) AS SiO2,
            MAX(CASE WHEN a.analyte_symbol = 'Al2O3'    THEN el.analyte_composition END) AS Al2O3,
            MAX(CASE WHEN a.analyte_symbol = 'Fe2O3'    THEN el.analyte_composition END) AS Fe2O3,
            MAX(CASE WHEN a.analyte_symbol = 'MnO'      THEN el.analyte_composition END) AS MnO,
            MAX(CASE WHEN a.analyte_symbol = 'MgO'      THEN el.analyte_composition END) AS MgO,
            MAX(CASE WHEN a.analyte_symbol = 'CaO'      THEN el.analyte_composition END) AS CaO,
            MAX(CASE WHEN a.analyte_symbol = 'Na2O'     THEN el.analyte_composition END) AS Na2O,
            MAX(CASE WHEN a.analyte_symbol = 'K2O'      THEN el.analyte_composition END) AS K2O,
            MAX(CASE WHEN a.analyte_symbol = 'TiO2'     THEN el.analyte_composition END) AS TiO2,
            MAX(CASE WHEN a.analyte_symbol = 'P2O5'     THEN el.analyte_composition END) AS P2O5,
            MAX(CASE WHEN a.analyte_symbol = 'LOI'      THEN el.analyte_composition END) AS LOI,
            MAX(CASE WHEN a.analyte_symbol = 'LOI2'     THEN el.analyte_composition END) AS LOI2,
            MAX(CASE WHEN a.analyte_symbol = 'Total'    THEN el.analyte_composition END) AS Total,
            MAX(CASE WHEN a.analyte_symbol = 'Total 2'  THEN el.analyte_composition END) AS Total_2,
            MAX(CASE WHEN a.analyte_symbol = 'Fe2O3(T)' THEN el.analyte_composition END) AS Fe2O3_T,
            MAX(CASE WHEN a.analyte_symbol = 'Sc'       THEN el.analyte_composition END) AS Sc,
            MAX(CASE WHEN a.analyte_symbol = 'Be'       THEN el.analyte_composition END) AS Be,
            MAX(CASE WHEN a.analyte_symbol = 'V'        THEN el.analyte_composition END) AS V,
            MAX(CASE WHEN a.analyte_symbol = 'Cr'       THEN el.analyte_composition END) AS Cr,
            MAX(CASE WHEN a.analyte_symbol = 'Co'       THEN el.analyte_composition END) AS Co,
            MAX(CASE WHEN a.analyte_symbol = 'Ni'       THEN el.analyte_composition END) AS Ni,
            MAX(CASE WHEN a.analyte_symbol = 'Cu'       THEN el.analyte_composition END) AS Cu,
            MAX(CASE WHEN a.analyte_symbol = 'Zn'       THEN el.analyte_composition END) AS Zn,
            MAX(CASE WHEN a.analyte_symbol = 'Ga'       THEN el.analyte_composition END) AS Ga,
            MAX(CASE WHEN a.analyte_symbol = 'Ge'       THEN el.analyte_composition END) AS Ge,
            MAX(CASE WHEN a.analyte_symbol = 'As'       THEN el.analyte_composition END) AS As,
            MAX(CASE WHEN a.analyte_symbol = 'Rb'       THEN el.analyte_composition END) AS Rb,
            MAX(CASE WHEN a.analyte_symbol = 'Sr'       THEN el.analyte_composition END) AS Sr,
            MAX(CASE WHEN a.analyte_symbol = 'Y'        THEN el.analyte_composition END) AS Y,
            MAX(CASE WHEN a.analyte_symbol = 'Zr'       THEN el.analyte_composition END) AS Zr,
            MAX(CASE WHEN a.analyte_symbol = 'Nb'       THEN el.analyte_composition END) AS Nb,
            MAX(CASE WHEN a.analyte_symbol = 'Mo'       THEN el.analyte_composition END) AS Mo,
            MAX(CASE WHEN a.analyte_symbol = 'Ag'       THEN el.analyte_composition END) AS Ag,
            MAX(CASE WHEN a.analyte_symbol = 'In'       THEN el.analyte_composition END) AS In_,
            MAX(CASE WHEN a.analyte_symbol = 'Sn'       THEN el.analyte_composition END) AS Sn,
            MAX(CASE WHEN a.analyte_symbol = 'Sb'       THEN el.analyte_composition END) AS Sb,
            MAX(CASE WHEN a.analyte_symbol = 'Cs'       THEN el.analyte_composition END) AS Cs,
            MAX(CASE WHEN a.analyte_symbol = 'Ba'       THEN el.analyte_composition END) AS Ba,
            MAX(CASE WHEN a.analyte_symbol = 'La'       THEN el.analyte_composition END) AS La,
            MAX(CASE WHEN a.analyte_symbol = 'Ce'       THEN el.analyte_composition END) AS Ce,
            MAX(CASE WHEN a.analyte_symbol = 'Pr'       THEN el.analyte_composition END) AS Pr,
            MAX(CASE WHEN a.analyte_symbol = 'Nd'       THEN el.analyte_composition END) AS Nd,
            MAX(CASE WHEN a.analyte_symbol = 'Sm'       THEN el.analyte_composition END) AS Sm,
            MAX(CASE WHEN a.analyte_symbol = 'Eu'       THEN el.analyte_composition END) AS Eu,
            MAX(CASE WHEN a.analyte_symbol = 'Gd'       THEN el.analyte_composition END) AS Gd,
            MAX(CASE WHEN a.analyte_symbol = 'Tb'       THEN el.analyte_composition END) AS Tb,
            MAX(CASE WHEN a.analyte_symbol = 'Dy'       THEN el.analyte_composition END) AS Dy,
            MAX(CASE WHEN a.analyte_symbol = 'Ho'       THEN el.analyte_composition END) AS Ho,
            MAX(CASE WHEN a.analyte_symbol = 'Er'       THEN el.analyte_composition END) AS Er,
            MAX(CASE WHEN a.analyte_symbol = 'Tm'       THEN el.analyte_composition END) AS Tm,
            MAX(CASE WHEN a.analyte_symbol = 'Yb'       THEN el.analyte_composition END) AS Yb,
            MAX(CASE WHEN a.analyte_symbol = 'Lu'       THEN el.analyte_composition END) AS Lu,
            MAX(CASE WHEN a.analyte_symbol = 'Hf'       THEN el.analyte_composition END) AS Hf,
            MAX(CASE WHEN a.analyte_symbol = 'Ta'       THEN el.analyte_composition END) AS Ta,
            MAX(CASE WHEN a.analyte_symbol = 'W'        THEN el.analyte_composition END) AS W,
            MAX(CASE WHEN a.analyte_symbol = 'Tl'       THEN el.analyte_composition END) AS Tl,
            MAX(CASE WHEN a.analyte_symbol = 'Pb'       THEN el.analyte_composition END) AS Pb,
            MAX(CASE WHEN a.analyte_symbol = 'Bi'       THEN el.analyte_composition END) AS Bi,
            MAX(CASE WHEN a.analyte_symbol = 'Th'       THEN el.analyte_composition END) AS Th,
            MAX(CASE WHEN a.analyte_symbol = 'U'        THEN el.analyte_composition END) AS U,
            MAX(CASE WHEN a.analyte_symbol = 'S'        THEN el.analyte_composition END) AS S,
            MAX(CASE WHEN a.analyte_symbol = 'C'        THEN el.analyte_composition END) AS C,
            MAX(CASE WHEN a.analyte_symbol = 'Pt'       THEN el.analyte_composition END) AS Pt,
            MAX(CASE WHEN a.analyte_symbol = 'Pd'       THEN el.analyte_composition END) AS Pd,
            MAX(CASE WHEN a.analyte_symbol = 'Au'       THEN el.analyte_composition END) AS Au
        FROM external_analyses ea
        JOIN elemental_analysis el ON el.external_analysis_id = ea.id
        JOIN analytes a             ON a.id = el.analyte_id
        WHERE ea.sample_id IS NOT NULL
        GROUP BY ea.sample_id, ea.id, ea.analysis_date, ea.laboratory, ea.analyst
    """),

    # ------------------------------------------------------------------
    # v_experiment_xrd
    # One row per mineral phase per timepoint per experiment (long format).
    # Mineral names are dynamic so a wide pivot is not feasible here.
    # Join key to other views: experiment_id.
    # ------------------------------------------------------------------
    ("v_experiment_xrd", """
        CREATE VIEW v_experiment_xrd AS
        SELECT
            xp.experiment_id,
            xp.time_post_reaction_days,
            xp.mineral_name,
            xp.amount      AS amount_pct,
            xp.rwp,
            xp.measurement_date
        FROM xrd_phases xp
        WHERE xp.experiment_fk IS NOT NULL
    """),

    # ------------------------------------------------------------------
    # v_sample_xrd
    # One row per mineral phase per sample (long format).
    # Covers Mode A XRD mineralogy and actlabs_xrd_report uploads, both of
    # which write XRDPhase rows keyed on (sample_id, mineral_name) with
    # time_post_reaction_days = NULL.
    # Join key to other sample views: sample_id.
    # ------------------------------------------------------------------
    ("v_sample_xrd", """
        CREATE VIEW v_sample_xrd AS
        SELECT
            si.sample_id,
            xp.mineral_name,
            xp.amount          AS amount_pct,
            ea.analysis_date,
            ea.laboratory,
            ea.analyst
        FROM xrd_phases xp
        JOIN external_analyses ea ON ea.id = xp.external_analysis_id
        JOIN sample_info si       ON si.sample_id = ea.sample_id
        WHERE ea.analysis_type = 'XRD'
          AND ea.sample_id IS NOT NULL
          AND xp.time_post_reaction_days IS NULL
    """),

    # ------------------------------------------------------------------
    # v_dim_timepoints
    # Conformed time dimension: one row per primary result timepoint per
    # experiment.  Sits between v_experiments and the result fact views
    # (v_results_scalar, v_results_h2, v_results_icp) so PowerBI report
    # authors have a single authoritative source for time-axis fields.
    # modification_note (issue #118 PR3) replaced the legacy per-result modification column (dropped by issue #122 PR-D):
    # it is read from the 'modification' notes on the result, joined with '; '
    # in id order when there is more than one (an upload's mirror and a
    # hand-written one can coexist -- different created_by).
    # ------------------------------------------------------------------
    ("v_dim_timepoints", """
        CREATE VIEW v_dim_timepoints AS
        SELECT
            er.id                                  AS result_id,
            e.experiment_id,
            er.time_post_reaction_days,
            er.time_post_reaction_bucket_days,
            er.cumulative_time_post_reaction_days,
            er.sample_tube_number,
            (SELECT string_agg(n.note_text, '; ' ORDER BY n.id)
             FROM experiment_notes n
             WHERE n.result_id = er.id
               AND n.note_type = 'modification') AS modification_note
        FROM experimental_results er
        JOIN experiments e ON e.id = er.experiment_fk
        WHERE er.is_primary_timepoint_result = TRUE
    """),

    # ------------------------------------------------------------------
    # v_results_scalar
    # One row per primary result timepoint.
    # Join key to v_results_h2 and v_results_icp: result_id.
    # ------------------------------------------------------------------
    ("v_results_scalar", """
        CREATE VIEW v_results_scalar AS
        SELECT
            er.id                                    AS result_id,
            e.experiment_id,
            er.experiment_fk,
            er.time_post_reaction_days,
            er.time_post_reaction_bucket_days,
            er.cumulative_time_post_reaction_days,
            sr."gross_ammonium_concentration_mM",
            sr."background_ammonium_concentration_mM",
            sr.grams_per_ton_yield,
            sr.final_ph,
            sr."final_nitrate_concentration_mM",
            sr.ferrous_iron_yield,
            sr.ferrous_iron_yield_h2_pct,
            SUM(COALESCE(sr.ferrous_iron_yield_h2_pct, 0)) OVER (
                PARTITION BY e.experiment_id
                ORDER BY er.cumulative_time_post_reaction_days, er.id
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS cumulative_ferrous_iron_yield_h2_pct,
            sr.ferrous_iron_yield_nh3_pct,
            sr."final_dissolved_oxygen_mg_L",
            sr."final_conductivity_mS_cm",
            sr."final_alkalinity_mg_L",
            sr."co2_partial_pressure_MPa",
            sr."sampling_volume_mL",
            sr.ammonium_quant_method,
            sr.background_experiment_fk,
            sr.measurement_date                      AS scalar_measurement_date,
            sr.nmr_run_date,
            GREATEST(0, sr."gross_ammonium_concentration_mM" - sr."background_ammonium_concentration_mM") AS net_ammonium_concentration
        FROM experimental_results er
        JOIN experiments e        ON e.id  = er.experiment_fk
        LEFT JOIN scalar_results sr ON sr.result_id = er.id
        WHERE er.is_primary_timepoint_result = TRUE
    """),

    # ------------------------------------------------------------------
    # v_results_scalar_rollup
    # One row per (base_experiment_id, timepoint bucket). Cross-replicate
    # mean/median/std for a replicate set (or a single non-replicate
    # experiment, which yields n_vials=1 and NULL std). Experiments
    # flagged is_outlier are excluded from all aggregates including the
    # counts (issue #70 P4) but stay in every per-row view.
    # No ICP aggregation (permanently out of scope).
    #
    # Counts (2026-08-01): the former single `n_replicates` column was
    # COUNT(sr.result_id) over a LEFT JOIN, which counted scalar ROWS -- not
    # replicates and not vials. It read 0 for ICP-only timepoints (335 phantom
    # groups in production) and over-counted wherever one vial held more than
    # one primary row. It is replaced by three unambiguous counts, because the
    # letter is the scientific unit while a '-t<days>' vial is one
    # destructively-sampled instance of it (MODELS.md, issue #98):
    #   n_vials             - distinct experiments contributing a scalar value
    #   n_replicate_letters - distinct replicate letters (0 when unlettered)
    #   n_values            - rows actually behind mean/median/sd
    # The JOIN to scalar_results is INNER so a timepoint with no scalar data
    # produces no row here at all. See
    # docs/issues/issue-rollup-replicate-count-and-null-timepoint-buckets.md
    # ------------------------------------------------------------------
    ("v_results_scalar_rollup", """
        CREATE VIEW v_results_scalar_rollup AS
        SELECT
            COALESCE(e.base_experiment_id, e.experiment_id)              AS base_experiment_id,
            er.time_post_reaction_bucket_days,
            COUNT(DISTINCT e.id)                                         AS n_vials,
            COUNT(DISTINCT e.replicate_label)                            AS n_replicate_letters,
            COUNT(*)                                                     AS n_values,
            AVG(sr."gross_ammonium_concentration_mM")                   AS "mean_gross_ammonium_mM",
            percentile_cont(0.5) WITHIN GROUP (
                ORDER BY sr."gross_ammonium_concentration_mM")          AS "median_gross_ammonium_mM",
            stddev_samp(sr."gross_ammonium_concentration_mM")           AS "sd_gross_ammonium_mM",
            AVG(GREATEST(0, sr."gross_ammonium_concentration_mM" - sr."background_ammonium_concentration_mM"))
                                                                        AS "mean_net_ammonium_mM",
            stddev_samp(GREATEST(0, sr."gross_ammonium_concentration_mM" - sr."background_ammonium_concentration_mM"))
                                                                        AS "sd_net_ammonium_mM",
            -- h2_concentration is invariant ppm (vol/vol) per MODELS.md; AVG is only
            -- meaningful because the unit never varies. If h2_concentration_unit ever
            -- becomes variable, this silently averages mixed units.
            AVG(sr.h2_concentration)                                    AS mean_h2_ppm,
            stddev_samp(sr.h2_concentration)                            AS sd_h2_ppm,
            AVG(sr.h2_micromoles)                                       AS mean_h2_micromoles,
            stddev_samp(sr.h2_micromoles)                               AS sd_h2_micromoles,
            AVG(sr.h2_grams_per_ton_yield)                              AS mean_h2_grams_per_ton,
            stddev_samp(sr.h2_grams_per_ton_yield)                      AS sd_h2_grams_per_ton,
            AVG(sr.ferrous_iron_yield_h2_pct)                           AS mean_fe_yield_h2_pct,
            stddev_samp(sr.ferrous_iron_yield_h2_pct)                   AS sd_fe_yield_h2_pct,
            AVG(sr.ferrous_iron_yield_nh3_pct)                          AS mean_fe_yield_nh3_pct,
            stddev_samp(sr.ferrous_iron_yield_nh3_pct)                  AS sd_fe_yield_nh3_pct,
            AVG(sr.grams_per_ton_yield)                                 AS mean_grams_per_ton_yield,
            stddev_samp(sr.grams_per_ton_yield)                         AS sd_grams_per_ton_yield,
            AVG(sr.final_ph)                                            AS mean_final_ph
        FROM experimental_results er
        JOIN experiments e     ON e.id  = er.experiment_fk
        JOIN scalar_results sr ON sr.result_id = er.id
        WHERE er.is_primary_timepoint_result = TRUE
          AND NOT COALESCE(e.is_outlier, false)
        GROUP BY COALESCE(e.base_experiment_id, e.experiment_id),
                 er.time_post_reaction_bucket_days
    """),

    # ------------------------------------------------------------------
    # v_results_h2
    # One row per primary result timepoint where H2 was measured.
    # Rows with no H2 concentration are excluded.
    # Join key to v_results_scalar: result_id.
    # ------------------------------------------------------------------
    ("v_results_h2", """
        CREATE VIEW v_results_h2 AS
        SELECT
            er.id                       AS result_id,
            e.experiment_id,
            er.experiment_fk,
            er.time_post_reaction_days,
            er.time_post_reaction_bucket_days,
            sr.h2_concentration,
            sr.h2_concentration_unit,
            sr.gas_sampling_volume_ml,
            sr."gas_sampling_pressure_MPa",
            sr.h2_micromoles,
            sr.h2_mass_ug,
            sr.h2_grams_per_ton_yield,
            sr.gc_run_date
        FROM experimental_results er
        JOIN experiments e      ON e.id  = er.experiment_fk
        JOIN scalar_results sr  ON sr.result_id = er.id
        WHERE er.is_primary_timepoint_result = TRUE
          AND sr.h2_concentration IS NOT NULL
    """),

    # ------------------------------------------------------------------
    # v_results_h2_bkg_adjusted (issue #144)
    # One row per primary H2 result (same population as v_results_h2) of a
    # sample group that has an h2_background_links row, with the linked
    # serum vial background subtracted. Sample outliers stay in (per-row).
    # Background modes:
    #   group - every experiment whose COALESCE(base_experiment_id,
    #           experiment_id) = background_base_id
    #   vial  - every experiment whose experiment_id with the '-t<days>'
    #           token peeled off (TIMEPOINT_TOKEN_SQL_PATTERN) =
    #           background_stem_id
    # Background stats (bkg CTE) are per (sample group, bucket) and EXCLUDE
    # is_outlier background vials. Each sample row takes the nearest
    # background bucket (ties go to the earlier bucket, no maximum gap);
    # bkg_time_gap_days = background bucket - sample bucket (signed).
    # A sample row with a NULL bucket, or no background bucket, or NULL
    # h2_micromoles, gets NULL net values.
    # Math (issue #144 spec): d = h2_micromoles - bkg mean (unclamped),
    # net = GREATEST(0, d), u = bkg stddev_samp (NULL when bkg n = 1).
    # g/t and Fe(II) yield scale d and u by 2.01588 / rock_mass_g and
    # 3 * 55.845 / 1e6 / total_ferrous_iron_g * 100, read from the SAMPLE's
    # experimental_conditions (1:1 via uq_conditions_experiment_fk); a zero
    # rock mass or Fe(II) gives NULL (NULLIF), matching Python's > 0 guard.
    # No adjusted ppm: bkg_mean_h2_ppm is reference only.
    # GREATEST ignores NULLs in Postgres (GREATEST(0, NULL) = 0), so every
    # clamp is wrapped in CASE WHEN x IS NOT NULL to keep a missing value NULL.
    # ------------------------------------------------------------------
    ("v_results_h2_bkg_adjusted", f"""
        CREATE VIEW v_results_h2_bkg_adjusted AS
        WITH s AS (
            SELECT
                er.id                                AS result_id,
                e.experiment_id,
                er.experiment_fk,
                l.base_experiment_id,
                er.time_post_reaction_bucket_days,
                CASE WHEN l.background_base_id IS NOT NULL
                     THEN 'group' ELSE 'vial' END    AS background_mode,
                COALESCE(l.background_base_id, l.background_stem_id)
                                                     AS background_ref,
                sr.h2_micromoles,
                2.01588 / NULLIF(ec.rock_mass_g, 0)  AS k_gpt,
                3 * 55.845 / 1e6 / NULLIF(ec.total_ferrous_iron_g, 0) * 100
                                                     AS k_fe
            FROM experimental_results er
            JOIN experiments e          ON e.id = er.experiment_fk
            JOIN scalar_results sr      ON sr.result_id = er.id
            JOIN h2_background_links l
                 ON l.base_experiment_id = COALESCE(e.base_experiment_id, e.experiment_id)
            LEFT JOIN experimental_conditions ec ON ec.experiment_fk = e.id
            WHERE er.is_primary_timepoint_result = TRUE
              AND sr.h2_concentration IS NOT NULL
        ),
        bkg AS (
            SELECT
                l.base_experiment_id                 AS sample_base,
                er.time_post_reaction_bucket_days    AS bucket,
                COUNT(*)                             AS n_values,
                AVG(sr.h2_concentration)             AS mean_ppm,
                AVG(sr.h2_micromoles)                AS mean_umol,
                stddev_samp(sr.h2_micromoles)        AS sd_umol
            FROM h2_background_links l
            JOIN experiments e ON
                 (l.background_base_id IS NOT NULL
                  AND COALESCE(e.base_experiment_id, e.experiment_id) = l.background_base_id)
              OR (l.background_stem_id IS NOT NULL
                  AND regexp_replace(e.experiment_id, '{TIMEPOINT_TOKEN_SQL_PATTERN}', '') = l.background_stem_id)
            JOIN experimental_results er ON er.experiment_fk = e.id
            JOIN scalar_results sr       ON sr.result_id = er.id
            WHERE er.is_primary_timepoint_result = TRUE
              AND sr.h2_micromoles IS NOT NULL
              AND er.time_post_reaction_bucket_days IS NOT NULL
              AND NOT COALESCE(e.is_outlier, false)
            GROUP BY l.base_experiment_id, er.time_post_reaction_bucket_days
        ),
        d AS (
            SELECT
                s.*,
                m.bucket                             AS bkg_time_bucket_days,
                m.bucket - s.time_post_reaction_bucket_days
                                                     AS bkg_time_gap_days,
                m.n_values                           AS bkg_n_values,
                m.mean_ppm                           AS bkg_mean_h2_ppm,
                m.mean_umol                          AS bkg_mean_h2_micromoles,
                m.sd_umol                            AS bkg_sd_h2_micromoles,
                s.h2_micromoles - m.mean_umol        AS d_umol
            FROM s
            LEFT JOIN LATERAL (
                SELECT b.bucket, b.n_values, b.mean_ppm, b.mean_umol, b.sd_umol
                FROM bkg b
                WHERE b.sample_base = s.base_experiment_id
                  AND s.time_post_reaction_bucket_days IS NOT NULL
                ORDER BY abs(b.bucket - s.time_post_reaction_bucket_days), b.bucket
                LIMIT 1
            ) m ON true
        )
        SELECT
            result_id,
            experiment_id,
            experiment_fk,
            base_experiment_id,
            time_post_reaction_bucket_days,
            background_mode,
            background_ref,
            bkg_time_bucket_days,
            bkg_time_gap_days,
            bkg_n_values,
            bkg_mean_h2_ppm,
            bkg_mean_h2_micromoles,
            bkg_sd_h2_micromoles,
            h2_micromoles,
            d_umol                                   AS net_h2_micromoles_unclamped,
            CASE WHEN d_umol IS NOT NULL THEN GREATEST(0, d_umol) END
                                                     AS net_h2_micromoles,
            bkg_sd_h2_micromoles                     AS u_bkg_h2_micromoles,
            CASE WHEN d_umol IS NOT NULL THEN GREATEST(0, d_umol) END * 2.01588
                                                     AS net_h2_mass_ug,
            d_umol * k_gpt                           AS net_h2_grams_per_ton_unclamped,
            CASE WHEN d_umol * k_gpt IS NOT NULL THEN GREATEST(0, d_umol * k_gpt) END
                                                     AS net_h2_grams_per_ton,
            bkg_sd_h2_micromoles * k_gpt             AS u_bkg_h2_grams_per_ton,
            d_umol * k_fe                            AS net_fe_yield_h2_pct_unclamped,
            CASE WHEN d_umol * k_fe IS NOT NULL THEN GREATEST(0, d_umol * k_fe) END
                                                     AS net_fe_yield_h2_pct,
            bkg_sd_h2_micromoles * k_fe              AS u_bkg_fe_yield_h2_pct,
            d_umol < 0                               AS below_background
        FROM d
    """),

    # ------------------------------------------------------------------
    # v_results_h2_bkg_adjusted_rollup (issue #144)
    # One row per (base_experiment_id, timepoint bucket) of a linked sample
    # group, read from v_results_h2_bkg_adjusted. Sample experiments flagged
    # is_outlier are excluded (as in v_results_scalar_rollup); rows with a
    # NULL bucket are dropped. n_values counts rows with a net value.
    # Background columns are constant within a sample bucket, so MIN() just
    # carries them through.
    # Mean: GREATEST(0, AVG(unclamped)), so negative replicates pull the
    # mean down before the clamp. SD combines replicate scatter with the
    # background SD: sqrt(stddev_samp(d)^2 + AVG(u)^2), each term COALESCEd
    # to 0, and NULL only when both terms are NULL.
    # The mean clamps are CASE-guarded too: no values gives NULL, not 0.
    # ------------------------------------------------------------------
    ("v_results_h2_bkg_adjusted_rollup", """
        CREATE VIEW v_results_h2_bkg_adjusted_rollup AS
        SELECT
            v.base_experiment_id,
            v.time_post_reaction_bucket_days,
            COUNT(v.net_h2_micromoles_unclamped)                        AS n_values,
            MIN(v.bkg_time_bucket_days)                                 AS bkg_time_bucket_days,
            MIN(v.bkg_time_gap_days)                                    AS bkg_time_gap_days,
            MIN(v.bkg_n_values)                                         AS bkg_n_values,
            MIN(v.bkg_mean_h2_micromoles)                               AS bkg_mean_h2_micromoles,
            MIN(v.bkg_sd_h2_micromoles)                                 AS bkg_sd_h2_micromoles,
            CASE WHEN AVG(v.net_h2_micromoles_unclamped) IS NOT NULL
                 THEN GREATEST(0, AVG(v.net_h2_micromoles_unclamped)) END             AS mean_net_h2_micromoles,
            CASE WHEN stddev_samp(v.net_h2_micromoles_unclamped) IS NULL
                      AND AVG(v.u_bkg_h2_micromoles) IS NULL THEN NULL
                 ELSE sqrt(power(COALESCE(stddev_samp(v.net_h2_micromoles_unclamped), 0), 2)
                           + power(COALESCE(AVG(v.u_bkg_h2_micromoles), 0), 2))
            END                                                         AS sd_net_h2_micromoles,
            CASE WHEN AVG(v.net_h2_grams_per_ton_unclamped) IS NOT NULL
                 THEN GREATEST(0, AVG(v.net_h2_grams_per_ton_unclamped)) END          AS mean_net_h2_grams_per_ton,
            CASE WHEN stddev_samp(v.net_h2_grams_per_ton_unclamped) IS NULL
                      AND AVG(v.u_bkg_h2_grams_per_ton) IS NULL THEN NULL
                 ELSE sqrt(power(COALESCE(stddev_samp(v.net_h2_grams_per_ton_unclamped), 0), 2)
                           + power(COALESCE(AVG(v.u_bkg_h2_grams_per_ton), 0), 2))
            END                                                         AS sd_net_h2_grams_per_ton,
            CASE WHEN AVG(v.net_fe_yield_h2_pct_unclamped) IS NOT NULL
                 THEN GREATEST(0, AVG(v.net_fe_yield_h2_pct_unclamped)) END           AS mean_net_fe_yield_h2_pct,
            CASE WHEN stddev_samp(v.net_fe_yield_h2_pct_unclamped) IS NULL
                      AND AVG(v.u_bkg_fe_yield_h2_pct) IS NULL THEN NULL
                 ELSE sqrt(power(COALESCE(stddev_samp(v.net_fe_yield_h2_pct_unclamped), 0), 2)
                           + power(COALESCE(AVG(v.u_bkg_fe_yield_h2_pct), 0), 2))
            END                                                         AS sd_net_fe_yield_h2_pct,
            AVG(v.net_h2_micromoles_unclamped) < 0                      AS below_background
        FROM v_results_h2_bkg_adjusted v
        JOIN experiments e ON e.id = v.experiment_fk
        WHERE NOT COALESCE(e.is_outlier, false)
          AND v.time_post_reaction_bucket_days IS NOT NULL
        GROUP BY v.base_experiment_id, v.time_post_reaction_bucket_days
    """),

    # ------------------------------------------------------------------
    # v_results_icp
    # One row per primary result timepoint where ICP data exists.
    # Fixed element columns exposed with _ppm suffix (s_ppm is still missing --
    # a known gap noted 2026-08-13, not fixed here).
    # icp_run_date is sourced from scalar_results (master upload field).
    # Join key to v_results_scalar: result_id.
    # ------------------------------------------------------------------
    ("v_results_icp", """
        CREATE VIEW v_results_icp AS
        SELECT
            er.id                       AS result_id,
            e.experiment_id,
            er.experiment_fk,
            er.time_post_reaction_days,
            er.time_post_reaction_bucket_days,
            icp.dilution_factor         AS icp_dilution_factor,
            icp.instrument_used         AS icp_instrument_used,
            icp.raw_label               AS icp_raw_label,
            icp.sample_date             AS icp_sample_date,
            sr.icp_run_date,
            icp.fe   AS fe_ppm,
            icp.si   AS si_ppm,
            icp.mg   AS mg_ppm,
            icp.ca   AS ca_ppm,
            icp.ni   AS ni_ppm,
            icp.cu   AS cu_ppm,
            icp.mo   AS mo_ppm,
            icp.zn   AS zn_ppm,
            icp.mn   AS mn_ppm,
            icp.cr   AS cr_ppm,
            icp.co   AS co_ppm,
            icp.al   AS al_ppm,
            icp.sr   AS sr_ppm,
            icp.y    AS y_ppm,
            icp.nb   AS nb_ppm,
            icp.sb   AS sb_ppm,
            icp.cs   AS cs_ppm,
            icp.ba   AS ba_ppm,
            icp.nd   AS nd_ppm,
            icp.gd   AS gd_ppm,
            icp.pt   AS pt_ppm,
            icp.rh   AS rh_ppm,
            icp.ir   AS ir_ppm,
            icp.pd   AS pd_ppm,
            icp.ru   AS ru_ppm,
            icp.os   AS os_ppm,
            icp.tl   AS tl_ppm,
            icp.ag   AS ag_ppm,
            icp.ce   AS ce_ppm,
            icp.k    AS k_ppm,
            icp.la   AS la_ppm,
            icp.na   AS na_ppm,
            icp.pb   AS pb_ppm,
            icp.sc   AS sc_ppm,
            icp.th   AS th_ppm,
            icp.v    AS v_ppm,
            icp.ti   AS ti_ppm
        FROM experimental_results er
        JOIN experiments e          ON e.id  = er.experiment_fk
        JOIN icp_results icp        ON icp.result_id = er.id
        LEFT JOIN scalar_results sr ON sr.result_id  = er.id
        WHERE er.is_primary_timepoint_result = TRUE
    """),

    # ------------------------------------------------------------------
    # v_notes (issue #118 PR3)
    # One row per experiment note, typed and optionally scoped to a result.
    # event_date (issue #122 PR-B) anchors a dated reactor modification.
    # Power BI's entry point for this domain: join experiment_id to
    # v_experiments and result_id to v_dim_timepoints / v_results_*.
    # needs_review = true marks rows the 020 backfill could not place with
    # certainty (the review queue); note_type is the enum as text.
    # ------------------------------------------------------------------
    ("v_notes", """
        CREATE VIEW v_notes AS
        SELECT
            n.id                 AS note_id,
            e.experiment_id,
            n.result_id,
            n.event_date,
            n.note_type::text    AS note_type,
            n.note_text,
            n.created_at,
            n.created_by,
            n.needs_review
        FROM experiment_notes n
        JOIN experiments e ON e.id = n.experiment_fk
    """),

    # ------------------------------------------------------------------
    # v_core_flood_samples (issue #132)
    # One row per primary timepoint of a Core Flood experiment, with
    # cross-sample run values computed over the whole run.
    # A run is one base ID (run_base_id = base_experiment_id) split across
    # sequential segment experiments (CF_020, CF_020-2, ...), ordered by
    # cumulative_time_post_reaction_days, then result_id.
    # is_variant: a `_Text` child of a segment (CF_020-5_Bypass1, parent
    # CF_020-5) -- a blank or bypass. Variant rows are shown with their raw
    # values, but every derived column is NULL on them and they are in their
    # own window partition, so they never shift the segments' sums.
    # Flow rule: flow_rate_mL_min is the rate over the interval ENDING at
    # that sample; 0 means a hold (is_hold_interval).
    # H2 basis: each sample's h2_grams_per_ton_yield is only the H2 collected
    # since the previous sample, which is why summing it gives cumulative H2
    # and dividing it by interval_days gives a rate.
    # Divisions use NULLIF(..., 0): a zero interval (two samples on one
    # cumulative day, e.g. a segment boundary) or a NULL/0 pore volume gives
    # NULL, not an error. A NULL liquid volume adds 0 to the running total.
    # Assumes one experimental_conditions row per experiment
    # (uq_conditions_experiment_fk).
    # ------------------------------------------------------------------
    ("v_core_flood_samples", """
        CREATE VIEW v_core_flood_samples AS
        WITH s AS (
            SELECT
                er.id                                  AS result_id,
                e.experiment_id,
                er.experiment_fk,
                e.base_experiment_id                   AS run_base_id,
                COALESCE(p.experiment_id IS NOT NULL
                         AND left(e.experiment_id, length(p.experiment_id) + 1)
                             = p.experiment_id || '_',
                         false)                        AS is_variant,
                er.time_post_reaction_days,
                er.cumulative_time_post_reaction_days,
                sr.measurement_date                    AS sample_date,
                sr.gc_run_date,
                er.sample_tube_number,
                er."flow_rate_mL_min",
                er."nitrogen_flow_rate_mL_min",
                er.inlet_pressure_psi,
                er.outlet_pressure_psi,
                er."permeability_flow_rate_mL_min",
                sr."sampling_volume_mL",
                sr.h2_concentration,
                sr.gas_sampling_volume_ml,
                sr."gas_sampling_pressure_MPa",
                sr.h2_micromoles,
                sr.h2_mass_ug,
                sr.h2_grams_per_ton_yield,
                sr.final_ph,
                sr."final_conductivity_mS_cm",
                ec."pore_volume_mL"
            FROM experimental_results er
            JOIN experiments e               ON e.id = er.experiment_fk
            LEFT JOIN experiments p          ON p.id = e.parent_experiment_fk
            JOIN experimental_conditions ec  ON ec.experiment_fk = e.id
            LEFT JOIN scalar_results sr      ON sr.result_id = er.id
            WHERE er.is_primary_timepoint_result = TRUE
              -- Same reading of Core Flood as database/reactor_slot.py::_SERIES_BY_TYPE
              -- (lowercase, whitespace collapsed); keep the two in sync.
              AND lower(btrim(regexp_replace(ec.experiment_type, '\\s+', ' ', 'g')))
                  IN ('core flood', 'coreflood', 'cf')
        ), w AS (
            SELECT
                s.*,
                s.cumulative_time_post_reaction_days
                    - COALESCE(LAG(s.cumulative_time_post_reaction_days) OVER win, 0)
                                                       AS interval_days,
                SUM(COALESCE(s."sampling_volume_mL", 0)) OVER win
                                                       AS "cumulative_liquid_volume_mL",
                SUM(COALESCE(s.h2_grams_per_ton_yield, 0)) OVER win
                                                       AS cumulative_h2_grams_per_ton
            FROM s
            WINDOW win AS (PARTITION BY run_base_id, is_variant
                           ORDER BY cumulative_time_post_reaction_days, result_id
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        )
        SELECT
            result_id,
            experiment_id,
            experiment_fk,
            run_base_id,
            is_variant,
            time_post_reaction_days,
            cumulative_time_post_reaction_days,
            sample_date,
            gc_run_date,
            sample_tube_number,
            "flow_rate_mL_min",
            "nitrogen_flow_rate_mL_min",
            inlet_pressure_psi,
            outlet_pressure_psi,
            "permeability_flow_rate_mL_min",
            "sampling_volume_mL",
            h2_concentration,
            gas_sampling_volume_ml,
            "gas_sampling_pressure_MPa",
            h2_micromoles,
            h2_mass_ug,
            h2_grams_per_ton_yield,
            final_ph,
            "final_conductivity_mS_cm",
            "pore_volume_mL",
            CASE WHEN is_variant THEN NULL ELSE interval_days END
                                                       AS interval_days,
            CASE WHEN is_variant THEN NULL ELSE "cumulative_liquid_volume_mL" END
                                                       AS "cumulative_liquid_volume_mL",
            CASE WHEN is_variant THEN NULL
                 ELSE "cumulative_liquid_volume_mL" / NULLIF("pore_volume_mL", 0) END
                                                       AS cumulative_pore_volumes,
            CASE WHEN is_variant THEN NULL ELSE cumulative_h2_grams_per_ton END
                                                       AS cumulative_h2_grams_per_ton,
            CASE WHEN is_variant THEN NULL
                 ELSE h2_grams_per_ton_yield / NULLIF(interval_days, 0) END
                                                       AS h2_grams_per_ton_per_day,
            CASE WHEN is_variant THEN NULL ELSE "flow_rate_mL_min" = 0 END
                                                       AS is_hold_interval
        FROM w
    """),
]

try:
    with engine.connect() as conn:
        # Drop all managed views plus the legacy monolithic view
        for view_name, _ in _VIEWS:
            conn.execute(text(f"DROP VIEW IF EXISTS {view_name} CASCADE;"))
        conn.execute(text("DROP VIEW IF EXISTS v_primary_experiment_results CASCADE;"))

        # Recreate all views
        for view_name, view_sql in _VIEWS:
            try:
                conn.execute(text(view_sql))
            except Exception as e:
                logger.error("Failed to create view %s: %s", view_name, e)
                raise

        conn.commit()
except Exception as e:
    logger.error("Reporting view creation failed: %s", e)

@event.listens_for(ChemicalAdditive, 'before_insert')
@event.listens_for(ChemicalAdditive, 'before_update')
def calculate_additive_derived_values(mapper, connection, target):
    """
    Automatically calculate derived values for ChemicalAdditive before insert or update.
    This includes mass conversions, molar calculations, concentrations, and catalyst-specific
    values (elemental_metal_mass, catalyst_percentage, catalyst_ppm).
    Uses the calculation registry to avoid coupling to legacy model methods.
    """
    from backend.services.calculations.registry import recalculate
    recalculate(target, None)

@event.listens_for(ExperimentalConditions, 'before_insert')
@event.listens_for(ExperimentalConditions, 'before_update')
def set_reactor_slot(mapper, connection, target):
    """Keep experimental_conditions.reactor_slot derived from (reactor_number, experiment_type).

    Issue #97. A mapper-level listener rather than per-write-site assignment,
    because "every path that writes reactor_number must remember to also update
    the slot" is precisely the failure mode the column exists to eliminate. This
    covers every path that loads an ExperimentalConditions instance and mutates
    its attributes: both bulk-upload parsers, the conditions router,
    experimental_conditions_service.py, and the legacy Streamlit app.

    Exception: a bulk `Query.update()` (Core UPDATE) compiles straight to SQL
    and does not invoke per-row mapper events, so it does NOT fire this
    listener. database/data_migrations/swap_reactor_4_7_015.py:96-109 is an
    existing precedent for that idiom. A future script changing
    reactor_number or experiment_type this way must either avoid
    Query.update() for those columns, or recompute reactor_slot explicitly in
    the same script.

    Same exception applies to a raw Core INSERT built from hand-assembled SQL
    text, e.g. scripts/migrate-sqlite-to-postgres.py:152-153, which runs
    `conn.execute(text(sql), values)` directly against the connection. That
    also compiles straight to SQL with no ORM instance involved, so this
    listener never fires and every row it inserts lands with reactor_slot
    NULL. `alembic upgrade head` will not repair this afterward if the DB is
    already stamped past the migration that backfills the column — see the
    warning in database/CLAUDE.md. General rule: **any** write that does not
    go through an ORM instance (bulk Query.update(), raw Core INSERT/UPDATE,
    direct SQL) leaves reactor_slot stale and must recompute it explicitly.

    Same pattern as calculate_additive_derived_values above: mutating a column
    attribute in before_insert/before_update is included in the emitted
    INSERT/UPDATE. Note the corollary — the value is only correct *after* a
    flush. Code needing the slot for values it has just assigned, before
    flushing, must call derive_reactor_slot directly.
    """
    from .reactor_slot import derive_reactor_slot
    target.reactor_slot = derive_reactor_slot(
        target.reactor_number, target.experiment_type, target.reactor_series
    )

@event.listens_for(Session, 'before_flush')
def update_experiment_lineage_on_flush(session, flush_context, instances):
    """
    Automatically update experiment lineage fields before flushing.

    This listener:
    1. Parses experiment IDs for new experiments
    2. Sets base_experiment_id, parent_experiment_fk, and replicate_label
    3. Updates orphaned derivations when a group parent (bare stem, or an
       explicit -0/-1 spelling) is created
    """
    from .models import Experiment
    from .lineage_utils import parse_experiment_id

    # Track group-parent stems being inserted, to update their derivations
    new_parent_stems = []

    # Process new experiments
    for obj in session.new:
        if isinstance(obj, Experiment) and obj.experiment_id:
            # Update lineage for this experiment
            update_experiment_lineage(session, obj)

            # Track if this row is a group parent (bare stem, or explicit -0/-1
            # spelling) so any pre-existing orphaned derivations can be linked.
            base_id, derivation_num, treatment_variant, replicate_label = parse_experiment_id(obj.experiment_id)
            is_parent_row = (
                treatment_variant is None
                and replicate_label is None
                and (derivation_num is None or derivation_num in (0, 1))
            )
            if is_parent_row:
                new_parent_stems.append(base_id or obj.experiment_id)

    # After processing new experiments, update any orphaned derivations
    # This handles the case where a derivation was created before its parent
    for stem in new_parent_stems:
        update_orphaned_derivations(session, stem) 