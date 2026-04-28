import logging
from sqlalchemy import event, text
from sqlalchemy.orm import Session, attributes
from .models import ExternalAnalysis, SampleInfo, ChemicalAdditive, ElementalAnalysis, Experiment
from .database import engine
from .lineage_utils import update_experiment_lineage, update_orphaned_derivations

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
    # experimental_conditions and the first note entry as the description.
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
             ORDER BY n.created_at ASC
             LIMIT 1) AS description
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
            ec.water_to_rock_ratio,
            ec.reactor_number,
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
    # ------------------------------------------------------------------
    ("v_dim_timepoints", """
        CREATE VIEW v_dim_timepoints AS
        SELECT
            er.id                                  AS result_id,
            e.experiment_id,
            er.time_post_reaction_days,
            er.time_post_reaction_bucket_days,
            er.cumulative_time_post_reaction_days,
            er.brine_modification_description
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
            er.description                           AS sampling_description,
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
    # v_results_icp
    # One row per primary result timepoint where ICP data exists.
    # All 27 fixed element columns exposed with _ppm suffix.
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
            icp.tl   AS tl_ppm
        FROM experimental_results er
        JOIN experiments e          ON e.id  = er.experiment_fk
        JOIN icp_results icp        ON icp.result_id = er.id
        LEFT JOIN scalar_results sr ON sr.result_id  = er.id
        WHERE er.is_primary_timepoint_result = TRUE
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

@event.listens_for(Session, 'before_flush')
def update_experiment_lineage_on_flush(session, flush_context, instances):
    """
    Automatically update experiment lineage fields before flushing.
    
    This listener:
    1. Parses experiment IDs for new experiments
    2. Sets base_experiment_id and parent_experiment_fk
    3. Updates orphaned derivations when a base experiment is created
    """
    from .models import Experiment
    
    # Track base experiments being inserted to update their derivations
    new_base_experiments = []
    
    # Process new experiments
    for obj in session.new:
        if isinstance(obj, Experiment) and obj.experiment_id:
            # Update lineage for this experiment
            update_experiment_lineage(session, obj)
            
            # Track if this is a potential base experiment (no derivation number)
            from .lineage_utils import parse_experiment_id
            _, derivation_num, _ = parse_experiment_id(obj.experiment_id)
            if derivation_num is None:
                new_base_experiments.append(obj.experiment_id)
    
    # After processing new experiments, update any orphaned derivations
    # This handles the case where a derivation was created before its base
    for base_exp_id in new_base_experiments:
        update_orphaned_derivations(session, base_exp_id) 