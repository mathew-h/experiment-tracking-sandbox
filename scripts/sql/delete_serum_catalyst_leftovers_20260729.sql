-- ============================================================================
-- Delete the 69 leftover SERUM_Catalyst experiment IDs (old numbering scheme)
--
-- Generated 2026-07-29 for Mat. Target: production `experiments` DB on the lab PC.
--
-- CONTEXT
--   The DB currently holds 149 SERUM_Catalyst rows: the 80 INTENDED IDs
--   (SERUM_Catalyst_001-010, replicates a/b/c, timepoints -t1/-t3/-t7/-t20) plus
--   69 leftovers from the earlier sequential numbering (…_002a-t3, _011a-t7,
--   _025a-t1 … _040-t20) that were meant to be renamed, not duplicated.
--   The 80 intended IDs ALREADY EXIST and are NOT touched by this script --
--   nothing needs to be recreated afterwards.
--
--   Eleven IDs appear in both numbering schemes (001a/b/c-t1, 003a/b/c-t7,
--   006-t3, 008-t20, 009a/b/c-t1). Each is a single row that is KEPT. Confirm
--   it describes the correct catalyst arm before running this -- see
--   scripts/sql/verify_serum_catalyst_target_state.sql, Section 5.
--
-- READ BEFORE RUNNING
--   0. Run verify_serum_catalyst_target_state.sql FIRST and resolve its output.
--   1. This is a WRITE script. The read-only psql role from docs/PSQL_ACCESS.md
--      cannot execute it -- connect as the app/owner role.
--   2. Take a dump first:  pg_dump -h <LAB_PC> -U <owner> -d experiments -Fc \
--                            -f experiments_predelete_20260729.dump
--   3. Stop the FastAPI Windows service (or accept that a concurrent write may
--      block on row locks) before running.
--   4. It runs inside a single transaction and ends with ROLLBACK. Read the
--      counts, then change the last line to COMMIT and re-run.
--
-- WHAT IT DOES NOT DO
--   - Does not delete files on disk. `result_files` and `analysis_files` rows are
--     removed, but the underlying uploads are orphaned -- clean those up
--     separately using the paths reported in Section 2.
--   - Does not touch `compounds`, `sample_info`, or `analytes` (shared reference
--     data). `experiments.sample_id` is a plain FK to sample_info and is left alone.
--   - Does not renumber `experiment_number`. Gaps will remain where the 69 rows
--     were; that column is a display sequence, not a key the team reads.
--   - Does not rewrite `base_experiment_id` on surviving rows. That column is a
--     parsed string, not an FK (see MODELS.md), so a surviving replicate can retain
--     a base ID whose parent row is gone. That is already the normal case for
--     letter-only replicate sets and needs no fix.
--
-- Child rows are deleted explicitly rather than relying on ON DELETE CASCADE,
-- because the initial Alembic migration created these FKs without ondelete
-- clauses -- the model-level `ondelete="CASCADE"` may or may not be present in
-- the deployed constraints. Explicit deletes work either way.
-- ============================================================================

\timing on
\set ON_ERROR_STOP on

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Target list
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE doomed_ids (experiment_id text PRIMARY KEY) ON COMMIT DROP;

INSERT INTO doomed_ids (experiment_id) VALUES
    ('SERUM_Catalyst_002a-t3'),
    ('SERUM_Catalyst_002b-t3'),
    ('SERUM_Catalyst_002c-t3'),
    ('SERUM_Catalyst_004a-t20'),
    ('SERUM_Catalyst_004b-t20'),
    ('SERUM_Catalyst_004c-t20'),
    ('SERUM_Catalyst_005-t1'),
    ('SERUM_Catalyst_007-t7'),
    ('SERUM_Catalyst_010a-t3'),
    ('SERUM_Catalyst_010b-t3'),
    ('SERUM_Catalyst_010c-t3'),
    ('SERUM_Catalyst_011a-t7'),
    ('SERUM_Catalyst_011b-t7'),
    ('SERUM_Catalyst_011c-t7'),
    ('SERUM_Catalyst_012a-t20'),
    ('SERUM_Catalyst_012b-t20'),
    ('SERUM_Catalyst_012c-t20'),
    ('SERUM_Catalyst_013-t1'),
    ('SERUM_Catalyst_014-t3'),
    ('SERUM_Catalyst_015-t7'),
    ('SERUM_Catalyst_016-t20'),
    ('SERUM_Catalyst_017a-t1'),
    ('SERUM_Catalyst_017b-t1'),
    ('SERUM_Catalyst_017c-t1'),
    ('SERUM_Catalyst_018a-t3'),
    ('SERUM_Catalyst_018b-t3'),
    ('SERUM_Catalyst_018c-t3'),
    ('SERUM_Catalyst_019a-t7'),
    ('SERUM_Catalyst_019b-t7'),
    ('SERUM_Catalyst_019c-t7'),
    ('SERUM_Catalyst_020a-t20'),
    ('SERUM_Catalyst_020b-t20'),
    ('SERUM_Catalyst_020c-t20'),
    ('SERUM_Catalyst_021-t1'),
    ('SERUM_Catalyst_022-t3'),
    ('SERUM_Catalyst_023-t7'),
    ('SERUM_Catalyst_024-t20'),
    ('SERUM_Catalyst_025a-t1'),
    ('SERUM_Catalyst_025b-t1'),
    ('SERUM_Catalyst_025c-t1'),
    ('SERUM_Catalyst_026a-t3'),
    ('SERUM_Catalyst_026b-t3'),
    ('SERUM_Catalyst_026c-t3'),
    ('SERUM_Catalyst_027a-t7'),
    ('SERUM_Catalyst_027b-t7'),
    ('SERUM_Catalyst_027c-t7'),
    ('SERUM_Catalyst_028a-t20'),
    ('SERUM_Catalyst_028b-t20'),
    ('SERUM_Catalyst_028c-t20'),
    ('SERUM_Catalyst_029-t1'),
    ('SERUM_Catalyst_030-t3'),
    ('SERUM_Catalyst_031-t7'),
    ('SERUM_Catalyst_032-t20'),
    ('SERUM_Catalyst_033a-t1'),
    ('SERUM_Catalyst_033b-t1'),
    ('SERUM_Catalyst_033c-t1'),
    ('SERUM_Catalyst_034a-t3'),
    ('SERUM_Catalyst_034b-t3'),
    ('SERUM_Catalyst_034c-t3'),
    ('SERUM_Catalyst_035a-t7'),
    ('SERUM_Catalyst_035b-t7'),
    ('SERUM_Catalyst_035c-t7'),
    ('SERUM_Catalyst_036a-t20'),
    ('SERUM_Catalyst_036b-t20'),
    ('SERUM_Catalyst_036c-t20'),
    ('SERUM_Catalyst_037-t1'),
    ('SERUM_Catalyst_038-t3'),
    ('SERUM_Catalyst_039-t7'),
    ('SERUM_Catalyst_040-t20')
ON CONFLICT DO NOTHING;

-- Resolve to primary keys.
CREATE TEMP TABLE doomed AS
SELECT e.id AS pk, e.experiment_id
FROM experiments e
JOIN doomed_ids d ON d.experiment_id = e.experiment_id;

CREATE UNIQUE INDEX ON doomed (pk);

-- IDs in the list that do NOT exist in the DB (typos, already deleted).
-- Expect this to be empty; investigate anything listed here before committing.
SELECT d.experiment_id AS not_found_in_db
FROM doomed_ids d
LEFT JOIN experiments e ON e.experiment_id = d.experiment_id
WHERE e.id IS NULL
ORDER BY 1;

-- Confirm what will be deleted.
-- Expect exactly 69.
SELECT count(*) AS experiments_to_delete FROM doomed;
SELECT d.experiment_id, e.experiment_number, e.status, e.researcher, e.date,
       e.base_experiment_id, e.replicate_label, e.id_timepoint_days, e.is_outlier
FROM doomed d JOIN experiments e ON e.id = d.pk
ORDER BY d.experiment_id;

-- ---------------------------------------------------------------------------
-- 2. Pre-flight impact report
-- ---------------------------------------------------------------------------
SELECT 'experimental_results' AS tbl, count(*) FROM experimental_results r JOIN doomed d ON d.pk = r.experiment_fk
UNION ALL SELECT 'scalar_results', count(*) FROM scalar_results s JOIN experimental_results r ON r.id = s.result_id JOIN doomed d ON d.pk = r.experiment_fk
UNION ALL SELECT 'icp_results', count(*) FROM icp_results i JOIN experimental_results r ON r.id = i.result_id JOIN doomed d ON d.pk = r.experiment_fk
UNION ALL SELECT 'result_files', count(*) FROM result_files f JOIN experimental_results r ON r.id = f.result_id JOIN doomed d ON d.pk = r.experiment_fk
UNION ALL SELECT 'experimental_conditions', count(*) FROM experimental_conditions c JOIN doomed d ON d.pk = c.experiment_fk
UNION ALL SELECT 'chemical_additives', count(*) FROM chemical_additives a JOIN experimental_conditions c ON c.id = a.experiment_id JOIN doomed d ON d.pk = c.experiment_fk
UNION ALL SELECT 'experiment_notes', count(*) FROM experiment_notes n JOIN doomed d ON d.pk = n.experiment_fk OR d.experiment_id = n.experiment_id
UNION ALL SELECT 'modifications_log', count(*) FROM modifications_log m JOIN doomed d ON d.pk = m.experiment_fk OR d.experiment_id = m.experiment_id
UNION ALL SELECT 'external_analyses', count(*) FROM external_analyses x JOIN doomed d ON d.pk = x.experiment_fk OR d.experiment_id = x.experiment_id
UNION ALL SELECT 'xrd_phases', count(*) FROM xrd_phases p JOIN doomed d ON d.pk = p.experiment_fk OR d.experiment_id = p.experiment_id
UNION ALL SELECT 'reactor_change_requests (will be NULLed)', count(*) FROM reactor_change_requests q JOIN doomed d ON d.experiment_id = q.experiment_id
UNION ALL SELECT 'OTHER experiments using these as background (will be NULLed)', count(*) FROM scalar_results s JOIN doomed d ON d.pk = s.background_experiment_fk
UNION ALL SELECT 'OTHER experiments parented to these (will be NULLed)', count(*) FROM experiments e JOIN doomed d ON d.pk = e.parent_experiment_fk WHERE e.id NOT IN (SELECT pk FROM doomed)
ORDER BY 1;

-- Files that will be orphaned on disk. Save this output before committing.
SELECT f.file_path, f.file_name
FROM result_files f
JOIN experimental_results r ON r.id = f.result_id
JOIN doomed d ON d.pk = r.experiment_fk
UNION ALL
SELECT af.file_path, af.file_name
FROM analysis_files af
JOIN external_analyses x ON x.id = af.external_analysis_id
JOIN doomed d ON d.pk = x.experiment_fk OR d.experiment_id = x.experiment_id
ORDER BY 1;

-- SAFETY CHECK: external_analyses rows that are BOTH experiment-linked and
-- sample-linked. Section 4 unlinks (does not delete) these so sample
-- characterization data survives. Expect empty for -t serum vials.
SELECT x.id, x.experiment_id, x.sample_id, x.analysis_type
FROM external_analyses x
JOIN doomed d ON d.pk = x.experiment_fk OR d.experiment_id = x.experiment_id
WHERE x.sample_id IS NOT NULL
ORDER BY x.id;

-- ---------------------------------------------------------------------------
-- 3. Break inbound references from SURVIVING rows
-- ---------------------------------------------------------------------------
UPDATE scalar_results s
SET background_experiment_fk = NULL, background_experiment_id = NULL
WHERE s.background_experiment_fk IN (SELECT pk FROM doomed);

UPDATE experiments e
SET parent_experiment_fk = NULL
WHERE e.parent_experiment_fk IN (SELECT pk FROM doomed);

UPDATE reactor_change_requests q
SET experiment_id = NULL
WHERE q.experiment_id IN (SELECT experiment_id FROM doomed);

-- ---------------------------------------------------------------------------
-- 4. External analyses and XRD
-- ---------------------------------------------------------------------------
-- Analyses to fully delete: experiment-linked only (no sample characterization).
CREATE TEMP TABLE doomed_analyses AS
SELECT x.id
FROM external_analyses x
JOIN doomed d ON d.pk = x.experiment_fk OR d.experiment_id = x.experiment_id
WHERE x.sample_id IS NULL;

-- Analyses shared with a sample: unlink from the experiment, keep the row.
UPDATE external_analyses x
SET experiment_fk = NULL, experiment_id = NULL
WHERE x.sample_id IS NOT NULL
  AND (x.experiment_fk IN (SELECT pk FROM doomed)
       OR x.experiment_id IN (SELECT experiment_id FROM doomed));

DELETE FROM xrd_phases p
WHERE p.experiment_fk IN (SELECT pk FROM doomed)
   OR p.experiment_id IN (SELECT experiment_id FROM doomed)
   OR p.external_analysis_id IN (SELECT id FROM doomed_analyses);

DELETE FROM xrd_analysis a WHERE a.external_analysis_id IN (SELECT id FROM doomed_analyses);
DELETE FROM elemental_analysis ea WHERE ea.external_analysis_id IN (SELECT id FROM doomed_analyses);
DELETE FROM analysis_files af WHERE af.external_analysis_id IN (SELECT id FROM doomed_analyses);
DELETE FROM external_analyses x WHERE x.id IN (SELECT id FROM doomed_analyses);

-- ---------------------------------------------------------------------------
-- 5. Results
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE doomed_results AS
SELECT r.id FROM experimental_results r JOIN doomed d ON d.pk = r.experiment_fk;

DELETE FROM result_files   f WHERE f.result_id IN (SELECT id FROM doomed_results);
DELETE FROM scalar_results s WHERE s.result_id IN (SELECT id FROM doomed_results);
DELETE FROM icp_results    i WHERE i.result_id IN (SELECT id FROM doomed_results);
DELETE FROM experimental_results r WHERE r.id IN (SELECT id FROM doomed_results);

-- ---------------------------------------------------------------------------
-- 6. Conditions and additives
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE doomed_conditions AS
SELECT c.id FROM experimental_conditions c JOIN doomed d ON d.pk = c.experiment_fk;

DELETE FROM chemical_additives a WHERE a.experiment_id IN (SELECT id FROM doomed_conditions);
DELETE FROM experimental_conditions c WHERE c.id IN (SELECT id FROM doomed_conditions);

-- ---------------------------------------------------------------------------
-- 7. Notes and audit log
-- ---------------------------------------------------------------------------
DELETE FROM experiment_notes n
WHERE n.experiment_fk IN (SELECT pk FROM doomed)
   OR n.experiment_id IN (SELECT experiment_id FROM doomed);

-- Drop this statement if you want to retain the audit trail for deleted rows.
DELETE FROM modifications_log m
WHERE m.experiment_fk IN (SELECT pk FROM doomed)
   OR m.experiment_id IN (SELECT experiment_id FROM doomed);

-- ---------------------------------------------------------------------------
-- 8. The experiments themselves
-- ---------------------------------------------------------------------------
DELETE FROM experiments e WHERE e.id IN (SELECT pk FROM doomed);

-- ---------------------------------------------------------------------------
-- 9. Post-delete verification (all three must return 0)
-- ---------------------------------------------------------------------------
SELECT count(*) AS experiments_remaining
FROM experiments e JOIN doomed_ids d ON d.experiment_id = e.experiment_id;

SELECT count(*) AS orphan_results
FROM experimental_results r
LEFT JOIN experiments e ON e.id = r.experiment_fk
WHERE e.id IS NULL;

SELECT count(*) AS orphan_conditions
FROM experimental_conditions c
LEFT JOIN experiments e ON e.id = c.experiment_fk
WHERE e.id IS NULL;

-- ---------------------------------------------------------------------------
-- 10. Finish
--     Review every output above, then swap ROLLBACK for COMMIT and re-run.
-- ---------------------------------------------------------------------------
ROLLBACK;
-- COMMIT;

-- After COMMIT: restart the FastAPI service so reporting views are recreated
-- (database/event_listeners.py runs on engine connect), then refresh Power BI.
