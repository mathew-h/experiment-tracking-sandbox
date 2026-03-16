from sqlalchemy import event, text
from sqlalchemy.orm import Session, attributes
from .models import ExternalAnalysis, SampleInfo, ChemicalAdditive, ElementalAnalysis, Experiment
from .database import engine
from .lineage_utils import update_experiment_lineage, update_orphaned_derivations

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

# Ensure additives summary view exists (SQLite) at import time
try:
    with engine.connect() as conn:
        conn.execute(text("DROP VIEW IF EXISTS v_experiment_additives_summary;"))
        conn.execute(text(
            """
            CREATE VIEW v_experiment_additives_summary AS
            SELECT e.experiment_id AS experiment_id,
                   GROUP_CONCAT(c.name || ' ' || CAST(a.amount AS TEXT) || ' ' || a.unit, '; ') AS additives_summary
            FROM chemical_additives a
            JOIN experimental_conditions ec ON ec.id = a.experiment_id
            JOIN experiments e ON e.id = ec.experiment_fk
            JOIN compounds c ON c.id = a.compound_id
            GROUP BY e.experiment_id;
            """
        ))
        conn.execute(text("DROP VIEW IF EXISTS v_primary_experiment_results;"))
        conn.execute(text(
            """
            CREATE VIEW v_primary_experiment_results AS
            WITH base AS (
                SELECT
                    er.id,
                    er.experiment_fk,
                    er.time_post_reaction_days,
                    COALESCE(er.time_post_reaction_bucket_days, ROUND(er.time_post_reaction_days, 4)) AS bucket_key,
                    er.time_post_reaction_bucket_days,
                    er.cumulative_time_post_reaction_days,
                    er.description,
                    er.created_at,
                    er.is_primary_timepoint_result
                FROM experimental_results er
                WHERE er.is_primary_timepoint_result = 1
            ),
            scalar_bucket AS (
                SELECT
                    er.experiment_fk,
                    COALESCE(er.time_post_reaction_bucket_days, ROUND(er.time_post_reaction_days, 4)) AS bucket_key,
                    sr.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY er.experiment_fk, COALESCE(er.time_post_reaction_bucket_days, ROUND(er.time_post_reaction_days, 4))
                        ORDER BY er.is_primary_timepoint_result DESC, er.id DESC
                    ) AS rn
                FROM experimental_results er
                JOIN scalar_results sr ON sr.result_id = er.id
            ),
            icp_bucket AS (
                SELECT
                    er.experiment_fk,
                    COALESCE(er.time_post_reaction_bucket_days, ROUND(er.time_post_reaction_days, 4)) AS bucket_key,
                    icp.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY er.experiment_fk, COALESCE(er.time_post_reaction_bucket_days, ROUND(er.time_post_reaction_days, 4))
                        ORDER BY er.is_primary_timepoint_result DESC, er.id DESC
                    ) AS rn
                FROM experimental_results er
                JOIN icp_results icp ON icp.result_id = er.id
            )
            SELECT
                e.experiment_id AS experiment_id,
                b.experiment_fk AS experiment_fk,
                b.id AS result_id,
                b.time_post_reaction_days AS time_post_reaction_days,
                b.time_post_reaction_bucket_days AS time_post_reaction_bucket_days,
                b.cumulative_time_post_reaction_days AS cumulative_time_post_reaction_days,
                b.description AS result_description,
                b.created_at AS result_created_at,

                -- Scalar Results (resolved by experiment + time bucket)
                sr.id AS scalar_result_id,
                sr.gross_ammonium_concentration_mM AS gross_ammonium_concentration_mM,
                sr.background_ammonium_concentration_mM AS background_ammonium_concentration_mM,
                sr.grams_per_ton_yield AS grams_per_ton_yield,
                sr.final_ph AS final_ph,
                sr.final_nitrate_concentration_mM AS final_nitrate_concentration_mM,
                sr.ferrous_iron_yield AS ferrous_iron_yield,
                sr.final_dissolved_oxygen_mg_L AS final_dissolved_oxygen_mg_L,
                sr.final_conductivity_mS_cm AS final_conductivity_mS_cm,
                sr.final_alkalinity_mg_L AS final_alkalinity_mg_L,
                sr.co2_partial_pressure_MPa AS co2_partial_pressure_MPa,
                sr.sampling_volume_mL AS sampling_volume_mL,
                sr.ammonium_quant_method AS ammonium_quant_method,
                sr.background_experiment_fk AS background_experiment_fk,
                sr.measurement_date AS scalar_measurement_date,

                -- Hydrogen Data
                sr.h2_concentration AS h2_concentration,
                sr.h2_concentration_unit AS h2_concentration_unit,
                sr.gas_sampling_volume_ml AS gas_sampling_volume_ml,
                sr.gas_sampling_pressure_MPa AS gas_sampling_pressure_MPa,
                sr.h2_micromoles AS h2_micromoles,
                sr.h2_mass_ug AS h2_mass_ug,
                sr.h2_grams_per_ton_yield AS h2_grams_per_ton_yield,

                -- ICP Results (resolved by experiment + time bucket)
                icp.id AS icp_result_id,
                icp.dilution_factor AS icp_dilution_factor,
                icp.raw_label AS icp_raw_label,
                icp.measurement_date AS icp_measurement_date,
                icp.sample_date AS icp_sample_date,
                icp.instrument_used AS icp_instrument_used,

                -- ICP Elements
                icp.fe AS icp_fe_ppm,
                icp.si AS icp_si_ppm,
                icp.ni AS icp_ni_ppm,
                icp.cu AS icp_cu_ppm,
                icp.mo AS icp_mo_ppm,
                icp.zn AS icp_zn_ppm,
                icp.mn AS icp_mn_ppm,
                icp.ca AS icp_ca_ppm,
                icp.cr AS icp_cr_ppm,
                icp.co AS icp_co_ppm,
                icp.mg AS icp_mg_ppm,
                icp.al AS icp_al_ppm,
                icp.sr AS icp_sr_ppm,
                icp.y AS icp_y_ppm,
                icp.nb AS icp_nb_ppm,
                icp.sb AS icp_sb_ppm,
                icp.cs AS icp_cs_ppm,
                icp.ba AS icp_ba_ppm,
                icp.nd AS icp_nd_ppm,
                icp.gd AS icp_gd_ppm,
                icp.pt AS icp_pt_ppm,
                icp.rh AS icp_rh_ppm,
                icp.ir AS icp_ir_ppm,
                icp.pd AS icp_pd_ppm,
                icp.ru AS icp_ru_ppm,
                icp.os AS icp_os_ppm,
                icp.tl AS icp_tl_ppm

            FROM base b
            JOIN experiments e ON e.id = b.experiment_fk
            LEFT JOIN scalar_bucket sr
                ON sr.experiment_fk = b.experiment_fk
               AND sr.bucket_key = b.bucket_key
               AND sr.rn = 1
            LEFT JOIN icp_bucket icp
                ON icp.experiment_fk = b.experiment_fk
               AND icp.bucket_key = b.bucket_key
               AND icp.rn = 1;
            """
        ))
        conn.commit()
except Exception:
    # Safe to ignore at import; view creation isn't critical at this moment
    pass

@event.listens_for(ChemicalAdditive, 'before_insert')
@event.listens_for(ChemicalAdditive, 'before_update')
def calculate_additive_derived_values(mapper, connection, target):
    """
    Automatically calculate derived values for ChemicalAdditive before insert or update.
    This includes mass conversions, molar calculations, concentrations, and catalyst-specific
    values (elemental_metal_mass, catalyst_percentage, catalyst_ppm).
    """
    target.calculate_derived_values()

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