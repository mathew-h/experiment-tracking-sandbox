# Milestone 2: Calculation Engine

**Owner:** api-developer (primary), db-architect (model cleanup review)
**Branch:** `feature/m2-calculation-engine`

**Objective:** Extract all derived-field calculation logic from SQLAlchemy model methods
into a dedicated `backend/services/calculations/` package. Models become pure storage.
A registry pattern lets M3 call `registry.recalculate(instance, session)` after writes.

**Tasks:**
1. Build `registry.py` — dispatch dict with `@register` decorator and `recalculate()` entry point
2. Implement `conditions_calcs.py` — water_to_rock_ratio
3. Implement `additive_calcs.py` — unit conversions, moles, concentration, catalyst fields, format_additives()
4. Implement `scalar_calcs.py` — H2 (PV=nRT), ammonium yield, h2_grams_per_ton_yield
5. Delete calculation methods from `chemicals.py`, `conditions.py`, `results.py`
6. Write full unit tests (~29 cases) — pure functions, no DB required
7. Create `docs/CALCULATIONS.md` — formula reference

**Acceptance criteria:**
- `pytest tests/services/calculations/ -v` passes all ~29 tests
- `python -c "from database.models.chemicals import ChemicalAdditive"` succeeds (no calc methods)
- `docs/CALCULATIONS.md` exists and documents all formulas
- No `@hybrid_property` or `calculate_*` methods remain in `database/models/`

**Test Writer Agent:** See `tests/services/calculations/` — full coverage provided in M2.

**Documentation Agent:** `docs/CALCULATIONS.md` created in this milestone. Keep it in sync
with `backend/services/calculations/` in future milestones.
