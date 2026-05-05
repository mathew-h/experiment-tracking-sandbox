# Bug: `parse_experiment_id` misclassifies base experiment IDs as sequential derivations

## Summary

`parse_experiment_id` in `database/lineage_utils.py` (lines 76–80) treats any trailing `-N` suffix as a sequential derivation number. This causes experiment IDs like `CF-015`, `CF-12`, and `CF-04` to be incorrectly parsed as derivatives of a phantom base, rather than recognized as standalone base experiments.

## Current Behavior

The function uses `rsplit('-', 1)` and unconditionally treats the rightmost segment as a derivation index if it parses as an integer:

- `CF-015` → `base='CF'`, `deriv=15` ❌ (should be a base experiment)
- `CF-12` → `base='CF'`, `deriv=12` → **linked as child of CF-04** in the migration output ❌
- `CF-04` → `base='CF'`, `deriv=4` ❌

The case `CF-015-2` works correctly because the rightmost segment (`2`) is a derivation, and `CF-015` is correctly recognized as the base at that point.

## Root Cause

The existing logic was written to support experiment ID patterns like `TEST-SAMPLE-001`, as enforced by:

```
tests/test_lineage_migration.py:133
assert parse_experiment_id("TEST-SAMPLE-001") == ("TEST-SAMPLE", 1, None)
```

This assumption breaks down for real naming conventions where a hyphen-separated number is part of the experiment's canonical name (e.g., `CF-015`, `HPHT_001`), not a derivation index.

## Proposed Fix

Only treat a trailing `-N` as a sequential derivation when the prefix already contains a complete base structure — specifically, when the prefix ends in `_<digits>` or `-<digits>`. Otherwise, treat the full string as a base experiment name.

**Expected behavior after fix:**

| ID | Result |
|---|---|
| `CF-015` | base ✓ (prefix `CF` does not end in digits) |
| `CF-12` | base ✓ |
| `CF-015-2` | sequential, base=`CF-015` ✓ |
| `HPHT_001-2` | sequential, base=`HPHT_001` ✓ |
| `HPHT_MH_001-2` | sequential, base=`HPHT_MH_001` ✓ |

## Files to Change

1. **`database/lineage_utils.py` lines 76–80** — update `parse_experiment_id` with the new prefix-check logic
2. **`tests/test_lineage_migration.py` lines 130, 133** — update or remove the two synthetic test cases (`COMPLEX-ID-TEST-3` and `TEST-SAMPLE-001`) that no longer reflect real experiment naming conventions

## Post-Fix Data Migration Required

The corrupted lineage records already in the database must be corrected. A targeted re-run of the lineage migration is needed for all `TYPE-NNN` style experiments that were incorrectly linked, including at minimum: `CF-015`, `CF-04`, `CF-12`, and any other experiments following the same pattern.

## Acceptance Criteria

- [ ] `parse_experiment_id("CF-015")` returns a base experiment (no derivation)
- [ ] `parse_experiment_id("CF-015-2")` returns `base='CF-015'`, `deriv=2`
- [ ] `parse_experiment_id("HPHT_001-2")` returns `base='HPHT_001'`, `deriv=2`
- [ ] Affected test cases in `test_lineage_migration.py` updated to match real naming conventions
- [ ] DB lineage re-migration run and corrupted parent-child links corrected
