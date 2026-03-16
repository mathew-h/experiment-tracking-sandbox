-- SQL Query to Identify Duplicate Sample IDs
-- Run this in any SQLite browser/tool to see duplicates

-- Count total samples
SELECT 'Total Samples:' as Metric, COUNT(*) as Count FROM sample_info;

-- Find potential duplicates by comparing variations
-- This query finds samples that differ only in case, hyphens, underscores, or spaces

WITH normalized_samples AS (
    SELECT 
        sample_id,
        -- Normalize: lowercase, remove hyphens, underscores, spaces
        LOWER(REPLACE(REPLACE(REPLACE(sample_id, '-', ''), '_', ''), ' ', '')) as normalized_id
    FROM sample_info
),
duplicate_groups AS (
    SELECT 
        normalized_id,
        COUNT(*) as duplicate_count,
        GROUP_CONCAT(sample_id, ' | ') as all_variants
    FROM normalized_samples
    GROUP BY normalized_id
    HAVING COUNT(*) > 1
)
SELECT 
    'Duplicate Groups:' as Metric,
    COUNT(*) as Count
FROM duplicate_groups
UNION ALL
SELECT 
    'Extra Duplicate Records:' as Metric,
    SUM(duplicate_count - 1) as Count
FROM duplicate_groups;

-- Show all duplicate groups with details
SELECT 
    normalized_id as 'Normalized ID',
    duplicate_count as 'Count',
    all_variants as 'Actual Sample IDs'
FROM (
    SELECT 
        LOWER(REPLACE(REPLACE(REPLACE(sample_id, '-', ''), '_', ''), ' ', '')) as normalized_id,
        COUNT(*) as duplicate_count,
        GROUP_CONCAT(sample_id, ' | ') as all_variants
    FROM sample_info
    GROUP BY LOWER(REPLACE(REPLACE(REPLACE(sample_id, '-', ''), '_', ''), ' ', ''))
    HAVING COUNT(*) > 1
)
ORDER BY duplicate_count DESC, normalized_id;

-- Expected sample count after deduplication
SELECT 
    'Expected After Merge:' as Metric,
    COUNT(DISTINCT LOWER(REPLACE(REPLACE(REPLACE(sample_id, '-', ''), '_', ''), ' ', ''))) as Count
FROM sample_info;

