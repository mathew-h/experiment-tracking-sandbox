---
paths:
  - "database/models/**"
  - "alembic/**"
---

# Schema Modification Checklist

**Before writing any code that touches the database models, READ and APPLY this checklist.**

**Reference:** `.claude/MEMORY.md` + `MODELS.md` (authoritative)

---

## Phase 1: Understand Current State

- [ ] Read `.claude/rules/MODELS.md` (index) and the `MODELS-<topic>.md` file it lists for the model you're modifying; field names and relationships come from the model file itself
- [ ] Read `.claude/MEMORY.md` Key Design Decisions section (locked patterns, do NOT rewrite)
- [ ] Run `git log --oneline database/models/ | head -20` — what's changed recently?
- [ ] Check `alembic/versions/` — when was the last schema change? What pattern was used?

---

## Phase 2: Ask Before Proceeding If...

**STOP and escalate to user if ANY of these are true:**

- [ ] Your change affects more than ONE model (e.g., renaming a column that's FK'd elsewhere)
- [ ] You need to modify a **locked model** (listed under "What Is Locked" in `.claude/CLAUDE.md`) without explicit user instruction
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
   - [ ] Document any non-obvious meaning of the new value in the relevant MODELS*.md file

4. Tests (tests/models/)
   - [ ] Model instantiation test with new field
   - [ ] If FK/relationship: verify constraint enforces
   - [ ] If unique constraint: verify duplicate rejects
   - [ ] Tests pass: pytest tests/models/ -v

5. Documentation (MODELS*.md)
   - [ ] The relevant `.claude/rules/MODELS*.md` file records the field's gotchas and rationale (not a bare field list — the model file is the field list)
```

### For Modifying Locked Models

**DO NOT attempt this without explicit user sign-off.**

---

## Phase 4: Validation

Run these from the project root with the venv active (one `pytest` process at a time — the test DB is shared):

```bash
# Fresh migration on clean DB
alembic upgrade head

# Verify downgrade works
alembic downgrade -1
alembic upgrade head

# Test ORM models (includes the migration view-parity tests)
pytest tests/models/ -v

# If views depend on your change, recreate them. There is NO create_reporting_views()
# function — earlier revisions of this checklist named one and it never existed. The
# views are dropped and recreated by a module-level block in database/event_listeners.py
# (see its `try:` around the _VIEWS loop), so importing the module in a fresh process
# re-runs it. Verified 2026-08-10 by dropping a view and watching this restore it:
python -c "import database.event_listeners"
```

---

## Phase 5: Merge Checklist (Code Revision Agent Verifies)

- [ ] All tests pass
- [ ] No breaking changes to API schemas
- [ ] Migration is purely additive (no drops/renames)
- [ ] Alembic downgrade works cleanly
- [ ] New fields have docstrings and type hints
- [ ] The relevant MODELS*.md file is updated
- [ ] No hardcoded values in migration
