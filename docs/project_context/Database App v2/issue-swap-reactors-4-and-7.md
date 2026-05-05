# Swap Reactor 4 and Reactor 7: Dashboard Update + Data Migration

## Summary

Reactors 4 and 7 have been physically swapped in the lab. The app must reflect this by (1) updating all reactor metadata/descriptions on the dashboard and (2) migrating all historical experiment records so that data previously attributed to reactor 4 is now attributed to reactor 7 and vice versa.

This migration must be treated as high-risk. Reversing it cleanly after the fact would be difficult, so the script and its tests must be exhaustive before it is run against production.

---

## Background

Reactors 4 and 7 were physically exchanged. The reactor identifiers in the database (IDs, display names, descriptions) now refer to the wrong physical units. Every historical experiment record that was run on what we call "Reactor 4" was actually run on the physical unit now labeled Reactor 7, and vice versa. Both the UI and the underlying data need to be corrected atomically.

---

## Requirements

### 1. Dashboard / UI Changes

- Swap the display descriptions (name, notes, specs, or any other descriptive metadata) for Reactor 4 and Reactor 7 in the reactor configuration table.
- The dashboard reactor status cards must correctly show the swapped labels after the change.
- Confirm that any Power BI views or SQL views that surface reactor metadata also reflect the swap.

### 2. Data Migration Script

Write a migration script (prefer Alembic or a standalone SQL/Python migration) that does the following atomically inside a single transaction:

1. **Identify** all experiment records currently assigned to `reactor_id = 4` and `reactor_id = 7`.
2. **Swap** the reactor assignments:
   - All records with `reactor_id = 4` → `reactor_id = 7`
   - All records with `reactor_id = 7` → `reactor_id = 4`
3. **Swap** reactor metadata (description, display name, any config fields) between the two reactor rows in the reactor table.
4. **Commit** only if all steps succeed; roll back the entire transaction on any error.

The script must be idempotent or clearly document that it is a one-time migration with a guard to prevent double-execution.

---

## Testing Requirements

> ⚠️ This migration is difficult to reverse cleanly once run against production. Test coverage must be exhaustive before the script is executed.

### Pre-migration validation
- [ ] Count of experiments per reactor before migration is recorded and asserted against post-migration counts (the totals per-reactor should be swapped, not lost).
- [ ] Checksums or row hashes on key derived fields (ammonium yield, H₂ yield, etc.) are captured pre- and post-migration to confirm no data mutation beyond the reactor assignment.

### Unit / integration tests
- [ ] Seed a test database with a known set of experiments split across reactor 4 and reactor 7 (including edge cases: experiments with null reactor, experiments shared across both reactors in the same run if applicable).
- [ ] Run the migration script against the test DB.
- [ ] Assert that all reactor-4 experiments are now reactor-7 and vice versa.
- [ ] Assert that reactor metadata rows have been correctly swapped (description, display name, config fields).
- [ ] Assert that no other reactor records were modified.
- [ ] Assert that the total experiment count is unchanged.
- [ ] Assert rollback behavior: introduce a deliberate failure mid-migration and confirm the DB is left in the original state.

### Power BI / SQL view validation
- [ ] Confirm that all SQL views that join on `reactor_id` still return correct, non-null results post-migration.
- [ ] Spot-check at least one known experiment in each reactor against expected yield values.

### Dry-run mode
- [ ] The migration script should support a `--dry-run` flag that prints what would change without committing, to allow a final human review before live execution.

---

## Acceptance Criteria

- [ ] Dashboard reactor cards and descriptions correctly reflect the physical swap.
- [ ] All historical experiment records previously on reactor 4 are now on reactor 7 and vice versa.
- [ ] Migration runs inside a single atomic transaction with rollback on failure.
- [ ] Pre/post row count and checksum assertions pass.
- [ ] All integration tests pass against a seeded test database.
- [ ] Rollback test passes.
- [ ] `--dry-run` output reviewed and approved by Mat before live execution.
- [ ] Power BI views verified post-migration.

---

## Notes

- Do not run against production without a full database backup taken immediately beforehand.
- The calculation engine (backend/services/calculations/) re-derives ammonium yield, H₂ yield, ferrous iron yield, and catalyst loadings from raw experiment fields. Confirm whether those derived fields reference `reactor_id` directly or only through the experiment record — if they reference it directly, they must be recalculated post-migration.
- Tag this issue for review before any code is merged.
