-- ============================================================================
-- VERIFY the 80 intended SERUM_Catalyst experiments against the two workbooks
--   20260728_SERUM_catalyst_001_006_renamed.xlsx
--   20260728_SERUM_catalyst_007_010.xlsx
--
-- READ-ONLY. Safe to run with the read-only psql role (docs/PSQL_ACCESS.md).
-- Run this BEFORE deleting anything. Every result set below should be empty
-- except Section 1 (which should report exactly 80 rows found, 0 missing).
--
-- Expected values are transcribed verbatim from the workbooks. Note the known
-- workbook defect flagged in Section 4.
-- ============================================================================

\set ON_ERROR_STOP on
\timing on

CREATE TEMP TABLE expected (
    experiment_id text PRIMARY KEY,
    status        text,
    initial_ph    double precision,
    rock_mass_g   double precision,
    temperature_c double precision,
    water_mL      double precision,
    compound      text,
    amount_mg     double precision
);

INSERT INTO expected VALUES
    ('SERUM_Catalyst_001a-t1','ONGOING',4,1,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_001a-t20','ONGOING',4,1,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_001a-t3','ONGOING',4,1,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_001a-t7','ONGOING',4,1,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_001b-t1','ONGOING',4,1,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_001b-t20','ONGOING',4,1,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_001b-t3','ONGOING',4,1,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_001b-t7','ONGOING',4,1,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_001c-t1','ONGOING',4,1,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_001c-t20','ONGOING',4,1,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_001c-t3','ONGOING',4,1,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_001c-t7','ONGOING',4,1,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_002-t1','ONGOING',4,0,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_002-t20','ONGOING',4,0,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_002-t3','ONGOING',4,0,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_002-t7','ONGOING',4,0,90,20,'Copper(II) Chloride Dihydrate',26.8),
    ('SERUM_Catalyst_003a-t1','QUEUED',9,1,90,20,'Nickel(II) Chloride Hexahydrate',40.5),
    ('SERUM_Catalyst_003a-t20','QUEUED',9,1,90,20,'Nickel(II) Chloride Hexahydrate',40.5),
    ('SERUM_Catalyst_003a-t3','QUEUED',9,1,90,20,'Nickel(II) Chloride Hexahydrate',40.5),
    ('SERUM_Catalyst_003a-t7','QUEUED',9,1,90,20,'Nickel(II) Chloride Hexahydrate',40.5),
    ('SERUM_Catalyst_003b-t1','QUEUED',9,1,90,20,'Nickel(II) Chloride Hexahydrate',40.5),
    ('SERUM_Catalyst_003b-t20','QUEUED',9,1,90,20,'Nickel(II) Chloride Hexahydrate',40.5),
    ('SERUM_Catalyst_003b-t3','QUEUED',9,1,90,20,'Nickel(II) Chloride Hexahydrate',40.5),
    ('SERUM_Catalyst_003b-t7','QUEUED',9,1,90,20,'Nickel(II) Chloride Hexahydrate',40.5),
    ('SERUM_Catalyst_003c-t1','QUEUED',9,1,90,20,'Nickel(II) Chloride Hexahydrate',40.5),
    ('SERUM_Catalyst_003c-t20','QUEUED',9,1,90,20,'Nickel(II) Chloride Hexahydrate',40.5),
    ('SERUM_Catalyst_003c-t3','QUEUED',9,1,90,20,'Nickel(II) Chloride Hexahydrate',40.5),
    ('SERUM_Catalyst_003c-t7','QUEUED',9,1,90,20,'Nickel(II) Chloride Hexahydrate',40.5),
    ('SERUM_Catalyst_004-t1','QUEUED',9,0,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_004-t20','QUEUED',9,0,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_004-t3','QUEUED',9,0,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_004-t7','QUEUED',9,0,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_005a-t1','ONGOING',12,1,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_005a-t20','ONGOING',12,1,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_005a-t3','ONGOING',12,1,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_005a-t7','ONGOING',12,1,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_005b-t1','ONGOING',12,1,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_005b-t20','ONGOING',12,1,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_005b-t3','ONGOING',12,1,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_005b-t7','ONGOING',12,1,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_005c-t1','ONGOING',12,1,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_005c-t20','ONGOING',12,1,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_005c-t3','ONGOING',12,1,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_005c-t7','ONGOING',12,1,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_006-t1','ONGOING',12,0,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_006-t20','ONGOING',12,0,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_006-t3','ONGOING',12,0,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_006-t7','ONGOING',12,0,90,20,'Chromium(III) chloride hexahydrate',51.3),
    ('SERUM_Catalyst_007a-t1','ONGOING',4,1,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_007a-t20','ONGOING',4,1,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_007a-t3','ONGOING',4,1,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_007a-t7','ONGOING',4,1,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_007b-t1','ONGOING',4,1,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_007b-t20','ONGOING',4,1,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_007b-t3','ONGOING',4,1,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_007b-t7','ONGOING',4,1,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_007c-t1','ONGOING',4,1,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_007c-t20','ONGOING',4,1,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_007c-t3','ONGOING',4,1,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_007c-t7','ONGOING',4,1,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_008-t1','ONGOING',4,0,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_008-t20','ONGOING',4,0,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_008-t3','ONGOING',4,0,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_008-t7','ONGOING',4,0,90,20,'Sodium Molybdate Dihydrate (Na2MoO4x2H2O)',25.2),
    ('SERUM_Catalyst_009a-t1','ONGOING',4,1,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_009a-t20','ONGOING',4,1,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_009a-t3','ONGOING',4,1,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_009a-t7','ONGOING',4,1,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_009b-t1','ONGOING',4,1,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_009b-t20','ONGOING',4,1,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_009b-t3','ONGOING',4,1,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_009b-t7','ONGOING',4,1,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_009c-t1','ONGOING',4,1,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_009c-t20','ONGOING',4,1,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_009c-t3','ONGOING',4,1,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_009c-t7','ONGOING',4,1,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_010-t1','ONGOING',4,0,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_010-t20','ONGOING',4,0,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_010-t3','ONGOING',4,0,90,20,'Vanadium(II) Chloride',30.9),
    ('SERUM_Catalyst_010-t7','ONGOING',4,0,90,20,'Vanadium(II) Chloride',30.9);

-- ---------------------------------------------------------------------------
-- 1. Do all 80 intended IDs exist?
-- ---------------------------------------------------------------------------
SELECT (SELECT count(*) FROM expected)                                    AS expected_total,
       (SELECT count(*) FROM expected x JOIN experiments e USING (experiment_id)) AS found_in_db;

SELECT x.experiment_id AS missing_from_db
FROM expected x LEFT JOIN experiments e USING (experiment_id)
WHERE e.id IS NULL ORDER BY 1;

-- ---------------------------------------------------------------------------
-- 2. Lineage sanity: base_experiment_id / replicate_label / id_timepoint_days
--    Expect base = SERUM_Catalyst_00N, label = a|b|c or NULL, timepoint = 1|3|7|20.
-- ---------------------------------------------------------------------------
SELECT e.experiment_id, e.base_experiment_id, e.replicate_label, e.id_timepoint_days,
       e.parent_experiment_fk, e.status, e.date, e.sample_id
FROM expected x JOIN experiments e USING (experiment_id)
ORDER BY e.base_experiment_id, e.id_timepoint_days, e.replicate_label NULLS FIRST;

-- Anything whose parsed timepoint disagrees with its own ID suffix.
SELECT e.experiment_id, e.id_timepoint_days
FROM expected x JOIN experiments e USING (experiment_id)
WHERE e.id_timepoint_days IS DISTINCT FROM
      split_part(split_part(e.experiment_id, '-t', 2), '_', 1)::double precision;

-- ---------------------------------------------------------------------------
-- 3. Conditions mismatches (pH, rock mass, temperature, water volume)
--    ***MOST IMPORTANT SECTION.*** Any row here means the workbook overwrite
--    did not land and the vial is described by the WRONG catalyst arm.
-- ---------------------------------------------------------------------------
SELECT x.experiment_id,
       c.initial_ph    AS db_ph,    x.initial_ph    AS xl_ph,
       c.rock_mass_g   AS db_rock,  x.rock_mass_g   AS xl_rock,
       c.temperature_c AS db_temp,  x.temperature_c AS xl_temp,
       c."water_volume_mL" AS db_water, x.water_mL   AS xl_water
FROM expected x
JOIN experiments e USING (experiment_id)
LEFT JOIN experimental_conditions c ON c.experiment_fk = e.id
WHERE c.id IS NULL
   OR c.initial_ph        IS DISTINCT FROM x.initial_ph
   OR c.rock_mass_g       IS DISTINCT FROM x.rock_mass_g
   OR c.temperature_c     IS DISTINCT FROM x.temperature_c
   OR c."water_volume_mL" IS DISTINCT FROM x.water_mL
ORDER BY 1;

-- ---------------------------------------------------------------------------
-- 4. Additive mismatches (compound identity and amount)
--
--    KNOWN WORKBOOK DEFECT: in 20260728_SERUM_catalyst_001_006_renamed.xlsx the
--    additives sheet assigns Chromium(III) chloride hexahydrate 51.3 mg to
--    SERUM_Catalyst_004-t1/t3/t7/t20. Per the experiments sheet note and the
--    pH 9 conditions, 004 is the NICKEL background and should be
--    Nickel(II) Chloride Hexahydrate 40.5 mg. Rows for 004 appearing here are
--    expected until the workbook is corrected.
-- ---------------------------------------------------------------------------
SELECT x.experiment_id,
       cm.name AS db_compound, x.compound AS xl_compound,
       a.amount AS db_amount, x.amount_mg AS xl_amount, a.unit AS db_unit
FROM expected x
JOIN experiments e USING (experiment_id)
LEFT JOIN experimental_conditions c ON c.experiment_fk = e.id
LEFT JOIN chemical_additives a ON a.experiment_id = c.id
LEFT JOIN compounds cm ON cm.id = a.compound_id
WHERE a.id IS NULL
   OR cm.name IS DISTINCT FROM x.compound
   OR a.amount IS DISTINCT FROM x.amount_mg
ORDER BY 1;

-- Any target experiment carrying MORE than one additive (double-applied upload).
SELECT e.experiment_id, count(*) AS additive_rows
FROM expected x JOIN experiments e USING (experiment_id)
JOIN experimental_conditions c ON c.experiment_fk = e.id
JOIN chemical_additives a ON a.experiment_id = c.id
GROUP BY 1 HAVING count(*) > 1 ORDER BY 1;

-- ---------------------------------------------------------------------------
-- 5. THE ELEVEN AMBIGUOUS IDs
--    These IDs exist in BOTH the old (wrong) and new (intended) numbering, so
--    the surviving row could describe either arm. Confirm each matches the
--    RIGHT-HAND expectation below.
--
--      SERUM_Catalyst_001a/b/c-t1  -> Cu, pH 4,  rock 1 g   (old = new, safe)
--      SERUM_Catalyst_003a/b/c-t7  -> Ni, pH 9,  rock 1 g
--      SERUM_Catalyst_006-t3       -> Cr, pH 12, rock 0 g
--      SERUM_Catalyst_008-t20      -> Mo, pH 4,  rock 0 g
--      SERUM_Catalyst_009a/b/c-t1  -> V,  pH 4,  rock 1 g
-- ---------------------------------------------------------------------------
SELECT e.experiment_id, c.initial_ph, c.rock_mass_g, cm.name AS compound, a.amount, a.unit,
       (SELECT string_agg(n.note_text, ' || ') FROM experiment_notes n WHERE n.experiment_fk = e.id) AS notes
FROM experiments e
LEFT JOIN experimental_conditions c ON c.experiment_fk = e.id
LEFT JOIN chemical_additives a ON a.experiment_id = c.id
LEFT JOIN compounds cm ON cm.id = a.compound_id
WHERE e.experiment_id IN (
    'SERUM_Catalyst_001a-t1','SERUM_Catalyst_001b-t1','SERUM_Catalyst_001c-t1',
    'SERUM_Catalyst_003a-t7','SERUM_Catalyst_003b-t7','SERUM_Catalyst_003c-t7',
    'SERUM_Catalyst_006-t3','SERUM_Catalyst_008-t20',
    'SERUM_Catalyst_009a-t1','SERUM_Catalyst_009b-t1','SERUM_Catalyst_009c-t1')
ORDER BY 1;

-- ---------------------------------------------------------------------------
-- 6. Does anything to be deleted actually hold data worth keeping?
--    Results/notes/analyses on the 69 leftover IDs. Expect all zero.
-- ---------------------------------------------------------------------------
SELECT e.experiment_id,
       (SELECT count(*) FROM experimental_results r WHERE r.experiment_fk = e.id)  AS results,
       (SELECT count(*) FROM experiment_notes n     WHERE n.experiment_fk = e.id)  AS notes,
       (SELECT count(*) FROM external_analyses xa   WHERE xa.experiment_fk = e.id) AS analyses
FROM experiments e
WHERE e.experiment_id LIKE 'SERUM\_Catalyst\_%'
  AND e.experiment_id NOT IN (SELECT experiment_id FROM expected)
ORDER BY 2 DESC, 3 DESC, 1;

-- ---------------------------------------------------------------------------
-- 7. Full inventory of every SERUM_Catalyst row, classified.
--    Sanity-check the counts: 80 keep / 69 delete / 149 total.
-- ---------------------------------------------------------------------------
SELECT CASE WHEN x.experiment_id IS NULL THEN 'DELETE (leftover)' ELSE 'KEEP (intended)' END AS bucket,
       count(*)
FROM experiments e LEFT JOIN expected x USING (experiment_id)
WHERE e.experiment_id LIKE 'SERUM\_Catalyst\_%'
GROUP BY 1 ORDER BY 1;

SELECT e.experiment_id, e.experiment_number, e.status,
       CASE WHEN x.experiment_id IS NULL THEN 'DELETE' ELSE 'KEEP' END AS disposition
FROM experiments e LEFT JOIN expected x USING (experiment_id)
WHERE e.experiment_id LIKE 'SERUM\_Catalyst\_%'
ORDER BY e.experiment_number;
