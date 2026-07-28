-- Prod audit queries for the open reactor/experiment_type tickets.
-- READ ONLY. Nothing here writes. Run against the lab PC's Postgres.
--
--   psql "postgresql://USER@HOST:5432/experiments" -f docs/issues/audit-queries.sql
--
-- Paste the output into:
--   docs/issues/issue-reactor-slot-identity-and-occupancy-uniqueness.md  (Verification)
--   docs/issues/issue-experiment-type-enum-binding.md                    (Prerequisite)

SET default_transaction_read_only = on;

\echo '=== Q1. Slots with more than one ONGOING experiment right now ==='
\echo '=== Must be empty before the uniqueness constraint can be added ==='
SELECT
  CASE WHEN ec.experiment_type = 'Core Flood' THEN 'CF' ELSE 'R' END
    || lpad(ec.reactor_number::text, 2, '0') AS slot,
  count(*)                      AS ongoing_count,
  array_agg(e.experiment_id)    AS experiment_ids,
  array_agg(ec.experiment_type) AS types,
  array_agg(e.date)             AS start_dates
FROM experiments e
JOIN experimental_conditions ec ON ec.experiment_fk = e.id
WHERE e.status = 'ONGOING'
  AND ec.reactor_number IS NOT NULL
GROUP BY 1
HAVING count(*) > 1
ORDER BY 1;

\echo ''
\echo '=== Q2. Every experiment_type value, with counts ==='
\echo '=== Decides whether the enum ticket is a constraint or a data migration ==='
SELECT experiment_type, count(*) AS n
FROM experimental_conditions
GROUP BY 1
ORDER BY n DESC;

\echo ''
\echo '=== Q3. Rows with a reactor_number the slot backfill cannot classify ==='
SELECT ec.experiment_type,
       count(*) AS n,
       array_agg(e.experiment_id ORDER BY e.experiment_id) AS experiment_ids
FROM experimental_conditions ec
JOIN experiments e ON e.id = ec.experiment_fk
WHERE ec.reactor_number IS NOT NULL
  AND (ec.experiment_type IS NULL
       OR ec.experiment_type NOT IN ('HPHT', 'Core Flood'))
GROUP BY 1
ORDER BY n DESC;

\echo ''
\echo '=== Q4. Context: current ONGOING occupancy, one row per slot ==='
\echo '=== Sanity-check against the dashboard grid; they should agree ==='
SELECT
  CASE WHEN ec.experiment_type = 'Core Flood' THEN 'CF' ELSE 'R' END
    || lpad(ec.reactor_number::text, 2, '0') AS slot,
  e.experiment_id,
  ec.experiment_type,
  e.date AS started,
  e.researcher
FROM experiments e
JOIN experimental_conditions ec ON ec.experiment_fk = e.id
WHERE e.status = 'ONGOING'
  AND ec.reactor_number IS NOT NULL
ORDER BY 1;
