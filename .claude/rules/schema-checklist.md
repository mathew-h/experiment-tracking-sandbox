# Schema Modification Checklist

**Before writing any code that touches the database models, READ and APPLY this checklist.**

**Reference:** `.claude/MEMORY.md` + `MODELS.md` (authoritative)

---

## Phase 1: Understand Current State

- [ ] Read `MODELS.md` for the field you're modifying (complete reference of all models, relationships, enums)
- [ ] Read `.claude/MEMORY.md` Key Design Decisions section (locked patterns, do NOT rewrite)
- [ ] Check `docs/sample_data/representative_sample.xlsx` if it exists — does your change account for all columns in it?
- [ ] Run `git log --oneline database/models/ | head -20` — what's changed recently?
- [ ] Check `alembic/versions/` — when was the last schema change? What pattern was used?

---

## Phase 2: Ask Before Proceeding If...

**STOP and escalate to user if ANY of these are true:**

- [ ] Your change affects more than ONE model (e.g., renaming a column that's FK'd elsewhere)
- [ ] You need to modify a **locked model** (listed in CLAUDE.md Section 4) without explicit user instruction
- [ ] You want to **flatten JSON columns** (ICPResults.all_elements, XRDAnalysis.mineral_phases) into separate tables
- [ ] You want to add a NEW THIRD-PARTY PACKAGE to requirements.txt
- [ ] Your migration requires a **destructive operation** (dropping a column, renaming, changing types)
- [ ] You're unsure whether a calculated field should be persisted or derived
- [ ] The change affects any **bulk upload parser** (backend/services/bulk_uploads/) logic

---

## Phase 3: Implement

### For Additive Changes (New Column, New Table, New Enum)

```
1. Model File (database/models/*.py)
   - [ ] Add field with type, nullable, default, constraints
   - [ ] Add relationship if needed
   - [ ] Add docstring explaining the field
   - [ ] Type hint is complete (no Any without comment)

2. Alembic Migration (alembic/versions/)
   - [ ] Create with: alembic revision --autogenerate -m "descriptive message"
   - [ ] Review generated migration carefully
   - [ ] Test: alembic upgrade head against fresh dev DB
   - [ ] Test downgrade: alembic downgrade -1 (should be clean)

3. Enum Changes (database/models/enums.py)
   - [ ] New enum value added
   - [ ] Migration created to add new constraint (if needed)
   - [ ] Document the new value in MODELS.md

4. Tests (tests/models/)
   - [ ] Model instantiation test with new field
   - [ ] If FK/relationship: verify constraint enforces
   - [ ] If unique constraint: verify duplicate rejects
   - [ ] Tests pass: pytest tests/models/ -v

5. Documentation (MODELS.md, FIELD_MAPPING.md)
   - [ ] MODELS.md updated with new field details
   - [ ] If it's a user-facing field: add to FIELD_MAPPING.md
```

### For Modifying Locked Models

**DO NOT attempt this without explicit user sign-off.**

---

## Phase 4: Validation

Run these commands in the Docker container:

```bash
# Fresh migration on clean DB
alembic upgrade head

# Verify downgrade works
alembic downgrade -1
alembic upgrade head

# Test ORM models
pytest tests/models/test_integrity.py -v

# If views depend on your change, recreate them:
python3 -c "from database.event_listeners import create_reporting_views; create_reporting_views()"

# Verify sample data still loads (Milestone 1 concern)
python3 scripts/migrate-sqlite-to-postgres.py
```

---

## Phase 5: Merge Checklist (Code Revision Agent Verifies)

- [ ] All tests pass
- [ ] No breaking changes to API schemas
- [ ] Migration is purely additive (no drops/renames)
- [ ] Alembic downgrade works cleanly
- [ ] New fields have docstrings and type hints
- [ ] MODELS.md is updated
- [ ] No hardcoded values in migration
