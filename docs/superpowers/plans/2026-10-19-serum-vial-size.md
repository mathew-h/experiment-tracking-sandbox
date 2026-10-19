# Serum Vial Size (`serum_vial_size_mL`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record the nominal serum vial size (whole mL) on `ExperimentalConditions` and carry it through the API, bulk-upload template, New Experiment wizard, Conditions tab and the `v_experiment_conditions` Power BI view.

**Architecture:** One additive nullable `Integer` column on a locked model (authorized by the spec). The Alembic migration adds the column and recreates `v_experiment_conditions` by hand, and its downgrade restores the old view **before** dropping the column. Validation (positive integer) lives in the Pydantic schemas and the UI only, with no DB `CHECK`. The bulk parser needs **no** edit because it maps conditions columns from the model; only the template changes. The "Serum only" rule is UI-only.

**Tech Stack:** SQLAlchemy 2 / Alembic / PostgreSQL, FastAPI + Pydantic 2.10.4, React 18 + TypeScript + Vitest + Testing Library.

**Spec:** `docs/issues/issue-serum_vial_size.md.txt` (read it alongside this plan; section numbers below refer to it).

**Branch:** `feat/serum-vial-size` (already cut from `develop` at `37ae701`). Mode: **inline**. Commit prefix: `[feat]`. PR: `gh pr create --base develop`.

## Global Constraints

- Column name is exactly `serum_vial_size_mL` (mixed case). Raw SQL must quote it: `ec."serum_vial_size_mL"`.
- Type `Integer`, `nullable=True`, no default, no backfill, **no DB `CHECK` constraint**.
- The stored value is the **nominal** size in whole mL (20, 60, 120, 160, ...), not the true total vial volume.
- No calculation reads it. Do not touch `backend/services/calculations/` or `docs/CALCULATIONS.md`.
- API/bulk accept the field on **any** experiment type. Do **not** add a type check like `_validate_reactor_number`.
- Validation: `Field(default=None, gt=0)` on `Optional[int]`. The API returns 422 for `0`, `-1`, `120.5`, accepts `120`, and coerces `120.0` → `120`.
- Only `v_experiment_conditions` gains the column, not `v_experiments`.
- Locked-component scope: `database/models/conditions.py` is the only model file changed. Nothing under `backend/services/bulk_uploads/`, `database/models/enums.py`, `auth/`, or any **existing** file in `alembic/versions/` changes.
- New Alembic revision ID: **`e9a4c1f7b3d2`**, `down_revision = "b8c4e2d7f9a1"` (verified the single head on 2026-10-19).
- Python tests: `.venv/Scripts/pytest` from the repo root. Never run two pytest processes at once (shared `experiments_test` DB).
- Frontend: `frontend/package.json` / `package-lock.json` must not change (no new deps).
- Do not write into `docs/project_context/`. The PostToolUse hook syncs `docs/**` edits made with Write/Edit. If a doc is edited via Bash/python, run the sync manually (see Task 6).

## Review Focus

1. **A Serum user enters a bad vial size, goes back to Step 1, and switches the type to HPHT.** The field is hidden, so it must not block Next, and the hidden stale value must not be sent. Covered by the Step 2 test "hidden invalid value does not block Next" (Task 4) and the `vialSizeForPayload` tests returning `undefined` for non-Serum (Task 4).
2. **A Master/bulk conditions column with a blank cell next to a filled one** makes pandas read the column as `float64`, so `120` arrives as `120.0`. It must still be stored as integer `120`, and the blank must stay NULL. Covered by `test_conditions_sheet_stores_serum_vial_size_as_int` (Task 3), which has a blank row on purpose.
3. **The downgrade after the API has run on the new code.** The view then depends on the column, and a bare `drop_column` fails. Covered by the Task 1 rehearsal, which imports `database.event_listeners` (simulating API start) before `downgrade -1`.
4. **A rejected PATCH must leave the stored value untouched** (no half-write). Covered by `test_patch_conditions_rejected_vial_size_leaves_value_unchanged` (Task 2).
5. **Template column alignment.** Inserting a header without the matching example-row cell shifts every later HPHT example value one column left. Covered by `test_new_experiments_template_conditions_sheet_headers`, which asserts the HPHT example's cell under `serum_vial_size_mL` is empty and `initial_conductivity_mS_cm` is still empty (Task 3).

---

## File Map

| File | Change | Task |
|---|---|---|
| `database/models/conditions.py` | + column after `water_volume_mL` (locked; spec authorizes) | 1 |
| `alembic/versions/e9a4c1f7b3d2_add_serum_vial_size_ml.py` | **new** migration (column + view, ordered downgrade) | 1 |
| `database/event_listeners.py` | + `ec."serum_vial_size_mL",` in `v_experiment_conditions` | 1 |
| `tests/models/test_serum_vial_size_column.py` | **new**: model column, single head, migration ↔ view SQL parity | 1 |
| `tests/views/test_experiment_conditions_view.py` | **new**: view string contains column | 1 |
| `backend/api/schemas/conditions.py` | + field on Create/Update/Response | 2 |
| `tests/api/test_conditions.py` | + POST/PATCH accept/reject tests | 2 |
| `backend/api/routers/bulk_uploads.py` | template header + example cell + INSTRUCTIONS row | 3 |
| `tests/api/test_bulk_uploads.py` | + conditions-sheet header test | 3 |
| `tests/services/bulk_uploads/test_new_experiments.py` | + int storage, mixed-case header, sequential inherit | 3 |
| `tests/test_replicate_creation_service.py` | + replicate copies value | 3 |
| `frontend/src/api/conditions.ts` | + `serum_vial_size_mL?: number` | 4 |
| `frontend/src/pages/NewExperiment/fieldVisibility.ts` | + union member, Serum set only | 4 |
| `frontend/src/pages/NewExperiment/vialSize.ts` | **new**: strict parse + payload helper | 4 |
| `frontend/src/pages/NewExperiment/Step2Conditions.tsx` | + input, inline error, disable Next | 4 |
| `frontend/src/pages/NewExperiment/index.tsx` | default, copy-from, payload | 4 |
| `frontend/src/pages/NewExperiment/__tests__/vialSize.test.ts` | **new** | 4 |
| `frontend/src/pages/NewExperiment/__tests__/Step2Conditions.test.tsx` | **new** | 4 |
| `frontend/src/pages/NewExperiment/__tests__/Step4Review.test.tsx` | fixture key + review row test | 4 |
| `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` | read row, seed, conditional modal input | 5 |
| `frontend/src/pages/ExperimentDetail/__tests__/ConditionsTab.buttons.test.tsx` | + read/modal visibility tests | 5 |
| `.claude/rules/MODELS.md`, `docs/POWERBI_MODEL.md`, `docs/upload_templates/new_experiments.md`, `docs/api/API_REFERENCE.md`, `docs/working/issue-log.md` | docs | 6 |

---

### Task 1: Model column, migration, reporting view

**Files:**
- Modify: `database/models/conditions.py:27`
- Create: `alembic/versions/e9a4c1f7b3d2_add_serum_vial_size_ml.py`
- Modify: `database/event_listeners.py:160`
- Test: `tests/models/test_serum_vial_size_column.py` (new), `tests/views/test_experiment_conditions_view.py` (new)

**Interfaces:**
- Produces: `ExperimentalConditions.serum_vial_size_mL` (`Integer`, nullable), Alembic revision `e9a4c1f7b3d2` with module constants `_V_CONDITIONS_OLD` / `_V_CONDITIONS_NEW`, and the view column `v_experiment_conditions."serum_vial_size_mL"`. Every later task depends on the model column.

- [ ] **Step 1: Write the failing tests**

Create `tests/models/test_serum_vial_size_column.py`:

```python
"""serum_vial_size_mL: nominal serum vial size on experimental_conditions
(docs/issues/issue-serum_vial_size.md.txt). Pins the column, the migration's
place in the chain, and that the migration's view SQL is the same view that
database/event_listeners.py recreates on API startup."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Integer

from database.models.conditions import ExperimentalConditions

REVISION = "e9a4c1f7b3d2"
PARENT = "b8c4e2d7f9a1"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _script_dir():
    return ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini")))


def _migration_module():
    path = REPO_ROOT / "alembic" / "versions" / f"{REVISION}_add_serum_vial_size_ml.py"
    spec = importlib.util.spec_from_file_location("_serum_vial_migration", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _norm(sql: str) -> str:
    return " ".join(sql.split())


def test_model_has_nullable_integer_column():
    col = ExperimentalConditions.__table__.columns["serum_vial_size_mL"]
    assert isinstance(col.type, Integer)
    assert col.nullable is True
    assert col.default is None and col.server_default is None


def test_alembic_has_a_single_head():
    # len()==1, not ==[REVISION], so the next migration doesn't break this test (E2/PR-D shape).
    assert len(_script_dir().get_heads()) == 1


def test_revision_revises_pr_d_drop():
    assert _script_dir().get_revision(REVISION).down_revision == PARENT


def test_migration_new_view_matches_startup_view():
    from database.event_listeners import _VIEWS

    mod = _migration_module()
    assert _norm(mod._V_CONDITIONS_NEW) == _norm(dict(_VIEWS)["v_experiment_conditions"])


def test_migration_old_view_is_new_view_minus_the_column():
    mod = _migration_module()
    assert 'ec."serum_vial_size_mL"' in mod._V_CONDITIONS_NEW
    assert 'serum_vial_size_mL' not in mod._V_CONDITIONS_OLD
    assert _norm(mod._V_CONDITIONS_NEW.replace('ec."serum_vial_size_mL",', "")) == _norm(
        mod._V_CONDITIONS_OLD
    )
```

Create `tests/views/test_experiment_conditions_view.py`:

```python
"""v_experiment_conditions exposes serum_vial_size_mL to Power BI; v_experiments
deliberately does not (docs/issues/issue-serum_vial_size.md.txt, settled decision 3)."""
from database.event_listeners import _VIEWS


def test_v_experiment_conditions_selects_serum_vial_size():
    sql = dict(_VIEWS)["v_experiment_conditions"]
    assert 'ec."serum_vial_size_mL"' in sql


def test_v_experiments_does_not_select_serum_vial_size():
    assert "serum_vial_size_mL" not in dict(_VIEWS)["v_experiments"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/models/test_serum_vial_size_column.py tests/views/test_experiment_conditions_view.py -v`
Expected: FAIL. The column tests fail with `KeyError: 'serum_vial_size_mL'`, `test_revision_revises_pr_d_drop` fails because the revision doesn't exist yet (the single-head test already passes), the migration tests fail with `FileNotFoundError`, and `test_v_experiment_conditions_selects_serum_vial_size` fails its assertion. `test_v_experiments_does_not_select_serum_vial_size` already passes, which is expected.

- [ ] **Step 3: Add the model column**

In `database/models/conditions.py`, directly after line 27 (`water_volume_mL = Column(Float)`), add:

```python
    serum_vial_size_mL = Column(Integer, nullable=True)  # Nominal serum vial size, whole mL. Tracking only; no calc reads it yet. NOT the true total vial volume.
```

`Integer` is already imported on line 1. Change nothing else in this file.

- [ ] **Step 4: Add the column to the startup view**

In `database/event_listeners.py`, inside the `v_experiment_conditions` SQL, change

```
            ec."water_volume_mL",
            ec.water_to_rock_ratio,
```

to

```
            ec."water_volume_mL",
            ec."serum_vial_size_mL",
            ec.water_to_rock_ratio,
```

(Scope this edit to the `v_experiment_conditions` block. `ec."water_volume_mL"` may appear in other views, which must not change.)

- [ ] **Step 5: Create the migration**

Create `alembic/versions/e9a4c1f7b3d2_add_serum_vial_size_ml.py`. Write it by hand rather than with `--autogenerate`: autogenerate against the dev DB picks up unrelated drift and never handles views.

```python
"""Add experimental_conditions.serum_vial_size_mL (nominal serum vial size).

Additive: one nullable Integer column holding the NOMINAL vial size in whole
mL (20, 60, 120, 160, ...). Tracking only -- no calculation reads it. No
backfill: existing rows stay NULL. No CHECK (> 0): the new-experiments
conditions-sheet loop has no per-row SAVEPOINT, so a constraint violation
would abort the transaction and break every remaining row of the sheet;
positive-integer validation lives in ConditionsCreate/ConditionsUpdate and
the UI instead. See docs/issues/issue-serum_vial_size.md.txt.

v_experiment_conditions is recreated in upgrade() so Power BI sees the column
right after the nightly `alembic upgrade head` (update.ps1), before the API
restarts. downgrade() restores the OLD view FIRST and only then drops the
column: once the API has started on the new code, database/event_listeners.py
has recreated the view selecting the column, and a bare drop_column fails with
"cannot drop column ... because other objects depend on it". No other view
selects from v_experiment_conditions, so CASCADE drops nothing else.

Revision ID: e9a4c1f7b3d2
Revises: b8c4e2d7f9a1
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e9a4c1f7b3d2"
down_revision: Union[str, None] = "b8c4e2d7f9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_V_CONDITIONS_OLD = """
    CREATE VIEW v_experiment_conditions AS
    SELECT
        e.experiment_id,
        ec.experiment_type,
        ec.temperature_c,
        ec.particle_size,
        ec.initial_ph,
        ec.rock_mass_g,
        ec."water_volume_mL",
        ec.water_to_rock_ratio,
        ec.reactor_number,
        ec.feedstock,
        ec.stir_speed_rpm,
        ec.room_temp_pressure_psi,
        ec.rxn_temp_pressure_psi,
        ec."co2_partial_pressure_MPa",
        ec.confining_pressure,
        ec.pore_pressure,
        ec.flow_rate,
        ec."initial_conductivity_mS_cm",
        ec.initial_nitrate_concentration,
        ec.initial_dissolved_oxygen,
        ec.initial_alkalinity,
        ec.core_height_cm,
        ec.core_width_cm,
        ec.core_volume_cm3,
        ec.total_ferrous_iron_g,
        ec.total_ferrous_iron
    FROM experiments e
    JOIN experimental_conditions ec ON ec.experiment_fk = e.id
"""

_V_CONDITIONS_NEW = """
    CREATE VIEW v_experiment_conditions AS
    SELECT
        e.experiment_id,
        ec.experiment_type,
        ec.temperature_c,
        ec.particle_size,
        ec.initial_ph,
        ec.rock_mass_g,
        ec."water_volume_mL",
        ec."serum_vial_size_mL",
        ec.water_to_rock_ratio,
        ec.reactor_number,
        ec.feedstock,
        ec.stir_speed_rpm,
        ec.room_temp_pressure_psi,
        ec.rxn_temp_pressure_psi,
        ec."co2_partial_pressure_MPa",
        ec.confining_pressure,
        ec.pore_pressure,
        ec.flow_rate,
        ec."initial_conductivity_mS_cm",
        ec.initial_nitrate_concentration,
        ec.initial_dissolved_oxygen,
        ec.initial_alkalinity,
        ec.core_height_cm,
        ec.core_width_cm,
        ec.core_volume_cm3,
        ec.total_ferrous_iron_g,
        ec.total_ferrous_iron
    FROM experiments e
    JOIN experimental_conditions ec ON ec.experiment_fk = e.id
"""


def _recreate(name: str, sql: str) -> None:
    op.execute(f"DROP VIEW IF EXISTS {name} CASCADE")
    op.execute(sql)


def upgrade() -> None:
    op.add_column(
        "experimental_conditions",
        sa.Column("serum_vial_size_mL", sa.Integer(), nullable=True),
    )
    _recreate("v_experiment_conditions", _V_CONDITIONS_NEW)


def downgrade() -> None:
    # Order matters: the view must stop depending on the column first.
    _recreate("v_experiment_conditions", _V_CONDITIONS_OLD)
    op.drop_column("experimental_conditions", "serum_vial_size_mL")
```

Before saving, diff `_V_CONDITIONS_OLD` against the current `v_experiment_conditions` block in `database/event_listeners.py` (as it was before Step 4: `git show develop:database/event_listeners.py`). The column list must match line for line.

- [ ] **Step 6: Rebuild the test DB schema**

`create_all` cannot add a column to an existing table, so `experiments_test` must be rebuilt once the model has changed:

```bash
.venv/Scripts/python -c "from database import Base; from sqlalchemy import create_engine; e=create_engine('postgresql://experiments_user:password@localhost:5432/experiments_test'); Base.metadata.drop_all(bind=e); Base.metadata.create_all(bind=e)"
```

If `drop_all` fails on view dependencies, reset as `postgres` instead: `DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO experiments_user;`.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/Scripts/pytest tests/models/test_serum_vial_size_column.py tests/views/test_experiment_conditions_view.py -v`
Expected: 7 passed.

Also run the existing single-head guard tests, which will now see a different head: `.venv/Scripts/pytest tests/models/ -v`.
Expected: `tests/models/test_legacy_result_columns_dropped.py::test_alembic_has_a_single_head` still passes (it checks `len(heads) == 1`). If any older test pins `get_heads() == ["b8c4e2d7f9a1"]` exactly, it fails here. Update it to `len(...) == 1`, matching the PR-D shape, and note it in the commit.

- [ ] **Step 8: Rehearse upgrade/downgrade on `experiments_test`**

The dev DB is stamped `b8c4e2d7f9a1`, but rehearse on the disposable test DB anyway. The rehearsal must drop the column to simulate the pre-change schema, which can't be done on dev. Write `<scratchpad>/rehearse_vial.py`. Save it with the Write tool, because long bash heredocs break:

```python
"""Rehearse e9a4c1f7b3d2 on experiments_test. Run with DATABASE_URL set to it."""
import os
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text

URL = os.environ["DATABASE_URL"]
assert URL.endswith("/experiments_test"), URL
eng = create_engine(URL)
ALEMBIC = [sys.executable, "-m", "alembic"]


def run(*args):
    print("$", *args, flush=True)
    subprocess.run(list(args), check=True)


def view_cols():
    with eng.connect() as c:
        return [r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'v_experiment_conditions' ORDER BY ordinal_position"))]


def table_col():
    cols = {c["name"]: c for c in inspect(eng).get_columns("experimental_conditions")}
    return cols.get("serum_vial_size_mL")


from database import Base  # noqa: E402  (import after URL check)
from database.models import Experiment, ExperimentalConditions  # noqa: E402
from database.models.enums import ExperimentStatus  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location(
    "m", "alembic/versions/e9a4c1f7b3d2_add_serum_vial_size_ml.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

from database.event_listeners import _VIEWS  # noqa: E402

# 1. Pre-change schema: tables from the model, one seeded row, then drop the new
#    column and install the OLD view (what production has today). Importing
#    `database` recreates every managed view, so drop them all before drop_all.
with eng.begin() as c:
    for name, _ in _VIEWS:
        c.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
Base.metadata.drop_all(eng)
Base.metadata.create_all(eng)
with Session(eng) as s:
    exp = Experiment(experiment_id="REHEARSE_VIAL_001", experiment_number=99901,
                     status=ExperimentStatus.ONGOING)
    s.add(exp); s.flush()
    s.add(ExperimentalConditions(experiment_id=exp.experiment_id, experiment_fk=exp.id,
                                 experiment_type="Serum", water_volume_mL=50.0))
    s.commit()
with eng.begin() as c:
    c.execute(text('ALTER TABLE experimental_conditions DROP COLUMN "serum_vial_size_mL"'))
    c.execute(text(m._V_CONDITIONS_OLD))
    c.execute(text("DROP TABLE IF EXISTS alembic_version"))
assert table_col() is None

# 2. upgrade
run(*ALEMBIC, "stamp", "b8c4e2d7f9a1")
run(*ALEMBIC, "upgrade", "head")
col = table_col()
assert col is not None and col["nullable"] and str(col["type"]) == "INTEGER", col
with eng.connect() as c:
    assert c.execute(text(
        'SELECT count(*) FROM experimental_conditions WHERE "serum_vial_size_mL" IS NOT NULL'
    )).scalar() == 0
    assert c.execute(text("SELECT count(*) FROM experimental_conditions")).scalar() == 1
    c.execute(text('SELECT experiment_id, "serum_vial_size_mL" FROM v_experiment_conditions')).all()
assert "serum_vial_size_mL" in view_cols()
print("UPGRADE OK")

# 3. Simulate API start on the new code: event_listeners recreates every view.
run(sys.executable, "-c", "import database.event_listeners")
assert "serum_vial_size_mL" in view_cols()

# 4. downgrade must succeed even though the view now depends on the column
run(*ALEMBIC, "downgrade", "-1")
assert table_col() is None
cols = view_cols()
assert cols and "serum_vial_size_mL" not in cols, cols
print("DOWNGRADE OK")

# 5. re-apply
run(*ALEMBIC, "upgrade", "head")
assert table_col() is not None and "serum_vial_size_mL" in view_cols()
print("RE-UPGRADE OK")

# 6. cleanup: leave experiments_test empty
with eng.begin() as c:
    for name, _ in _VIEWS:
        c.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
    c.execute(text("DROP TABLE IF EXISTS alembic_version"))
Base.metadata.drop_all(eng)
print("REHEARSAL PASSED")
```

Run from the repo root (no pipes, so a failure isn't masked):

```bash
DATABASE_URL=postgresql://experiments_user:password@localhost:5432/experiments_test PYTHONPATH=. .venv/Scripts/python <scratchpad>/rehearse_vial.py > <scratchpad>/rehearse_vial_out.txt 2>&1; echo "exit=$?"; tail -5 <scratchpad>/rehearse_vial_out.txt
```

Expected: `exit=0` and the last line `REHEARSAL PASSED`. Noisy view-creation errors logged on import against the empty DB are harmless. Afterwards, rebuild the test schema again (Step 6 command) so later test runs start from a clean `create_all`.

- [ ] **Step 9: Commit**

```bash
git add database/models/conditions.py database/event_listeners.py alembic/versions/e9a4c1f7b3d2_add_serum_vial_size_ml.py tests/models/test_serum_vial_size_column.py tests/views/test_experiment_conditions_view.py
git commit -F <scratchpad>/msg_task1.txt
```

`msg_task1.txt`:

```
[feat] Add serum_vial_size_mL conditions column

- Nullable Integer on experimental_conditions (locked model; additive,
  authorized by docs/issues/issue-serum_vial_size.md.txt)
- Migration e9a4c1f7b3d2 recreates v_experiment_conditions; downgrade
  restores the old view before dropping the column
- Rehearsed upgrade/downgrade/upgrade on experiments_test
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 2: API schemas and validation

**Files:**
- Modify: `backend/api/schemas/conditions.py:4,13,39,69`
- Test: `tests/api/test_conditions.py` (append)

**Interfaces:**
- Consumes: `ExperimentalConditions.serum_vial_size_mL` (Task 1).
- Produces: `ConditionsCreate.serum_vial_size_mL: Optional[int]` (gt=0), `ConditionsUpdate.serum_vial_size_mL: Optional[int]` (gt=0), `ConditionsResponse.serum_vial_size_mL: Optional[int]`. The frontend (Tasks 4–5) reads and writes the JSON key `serum_vial_size_mL`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_conditions.py`. The `COND_SLOT_` prefix is deliberate: the file's autouse `_cleanup_slot_rows` fixture deletes those rows, because the router commits.

```python
# --- serum_vial_size_mL validation (docs/issues/issue-serum_vial_size.md.txt) ---


def _vial_loc_in_detail(resp) -> bool:
    return any("serum_vial_size_mL" in err.get("loc", []) for err in resp.json()["detail"])


@pytest.mark.parametrize("bad, eid, num", [
    (0, "COND_SLOT_VIAL_P0", 38201),
    (-1, "COND_SLOT_VIAL_PM1", 38202),
    (120.5, "COND_SLOT_VIAL_PFRAC", 38203),
])
def test_create_conditions_rejects_invalid_serum_vial_size(client, db_session, bad, eid, num):
    exp = _make_experiment(db_session, eid=eid, num=num)
    resp = client.post("/api/conditions", json={
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "experiment_type": "Serum",
        "serum_vial_size_mL": bad,
    })
    assert resp.status_code == 422
    assert _vial_loc_in_detail(resp)


def test_create_conditions_accepts_serum_vial_size(client, db_session):
    exp = _make_experiment(db_session, eid="COND_SLOT_VIAL_OK", num=38204)
    resp = client.post("/api/conditions", json={
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "experiment_type": "Serum",
        "serum_vial_size_mL": 120,
    })
    assert resp.status_code == 201
    assert resp.json()["serum_vial_size_mL"] == 120


def test_create_conditions_coerces_whole_float_vial_size(client, db_session):
    exp = _make_experiment(db_session, eid="COND_SLOT_VIAL_WHOLE", num=38205)
    resp = client.post("/api/conditions", json={
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "experiment_type": "Serum",
        "serum_vial_size_mL": 120.0,
    })
    assert resp.status_code == 201
    body = resp.json()["serum_vial_size_mL"]
    assert body == 120 and isinstance(body, int)


def test_create_conditions_allows_vial_size_on_hpht(client, db_session):
    """UI-only scoping is intentional: the API takes the field on any type."""
    exp = _make_experiment(db_session, eid="COND_SLOT_VIAL_HPHT", num=38206)
    resp = client.post("/api/conditions", json={
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "experiment_type": "HPHT",
        "serum_vial_size_mL": 60,
    })
    assert resp.status_code == 201
    assert resp.json()["serum_vial_size_mL"] == 60


def test_conditions_response_vial_size_defaults_to_null(client, db_session):
    exp = _make_experiment(db_session, eid="COND_SLOT_VIAL_NULL", num=38207)
    resp = client.post("/api/conditions", json={
        "experiment_fk": exp.id,
        "experiment_id": exp.experiment_id,
        "experiment_type": "Serum",
    })
    assert resp.status_code == 201
    assert resp.json()["serum_vial_size_mL"] is None


def _create_serum_conditions(client, db_session, eid, num, vial=None):
    exp = _make_experiment(db_session, eid=eid, num=num)
    payload = {"experiment_fk": exp.id, "experiment_id": exp.experiment_id,
               "experiment_type": "Serum"}
    if vial is not None:
        payload["serum_vial_size_mL"] = vial
    resp = client.post("/api/conditions", json=payload)
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.parametrize("bad, eid, num", [
    (0, "COND_SLOT_VIAL_X0", 38211),
    (-1, "COND_SLOT_VIAL_XM1", 38212),
    (120.5, "COND_SLOT_VIAL_XFRAC", 38213),
])
def test_patch_conditions_rejects_invalid_serum_vial_size(client, db_session, bad, eid, num):
    cid = _create_serum_conditions(client, db_session, eid, num)
    resp = client.patch(f"/api/conditions/{cid}", json={"serum_vial_size_mL": bad})
    assert resp.status_code == 422
    assert _vial_loc_in_detail(resp)


def test_patch_conditions_accepts_serum_vial_size(client, db_session):
    cid = _create_serum_conditions(client, db_session, "COND_SLOT_VIAL_XOK", 38214)
    resp = client.patch(f"/api/conditions/{cid}", json={"serum_vial_size_mL": 160})
    assert resp.status_code == 200
    assert resp.json()["serum_vial_size_mL"] == 160


def test_patch_conditions_rejected_vial_size_leaves_value_unchanged(client, db_session):
    cid = _create_serum_conditions(client, db_session, "COND_SLOT_VIAL_XKEEP", 38215, vial=120)
    bad = client.patch(f"/api/conditions/{cid}", json={"serum_vial_size_mL": 0})
    assert bad.status_code == 422
    assert client.get(f"/api/conditions/{cid}").json()["serum_vial_size_mL"] == 120
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/api/test_conditions.py -v -k vial`
Expected: FAIL. The reject cases return 201 (Pydantic ignores the unknown key), and the accept cases hit `KeyError: 'serum_vial_size_mL'` on the response.

- [ ] **Step 3: Implement the schema fields**

In `backend/api/schemas/conditions.py`:

Line 4: `from pydantic import BaseModel, ConfigDict` → `from pydantic import BaseModel, ConfigDict, Field`

In `ConditionsCreate`, after `water_volume_mL: Optional[float] = None` (line 13):

```python
    # Nominal serum vial size, whole mL. Positive-integer only; 120.0 coerces to
    # 120, 120.5 is rejected. Accepted on any experiment type -- "Serum only" is
    # a UI rule, not an API rule.
    serum_vial_size_mL: Optional[int] = Field(default=None, gt=0)
```

In `ConditionsUpdate`, after `water_volume_mL: Optional[float] = None` (line 39):

```python
    serum_vial_size_mL: Optional[int] = Field(default=None, gt=0)
```

In `ConditionsResponse`, after `water_volume_mL: Optional[float] = None` (line 69):

```python
    serum_vial_size_mL: Optional[int] = None
```

No router change. `ExperimentalConditions(**payload.model_dump())` and the PATCH `setattr` loop pass the field through.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/api/test_conditions.py -v`
Expected: all pass (the 11 new tests plus every existing test in the file).

- [ ] **Step 5: Commit**

```bash
git add backend/api/schemas/conditions.py tests/api/test_conditions.py
git commit -F <scratchpad>/msg_task2.txt
```

```
[feat] Accept serum_vial_size_mL on conditions API

- Optional[int] with gt=0 on Create/Update; 422 for 0, -1, 120.5
- No experiment-type check (UI-only scoping)
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 3: Bulk-upload template and pass-through pinning tests

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py:948-973` (conditions headers + example row), `:1020` (INSTRUCTIONS)
- Test: `tests/api/test_bulk_uploads.py` (after line 1040), `tests/services/bulk_uploads/test_new_experiments.py` (append), `tests/test_replicate_creation_service.py` (append in class)

**Interfaces:**
- Consumes: the model column (Task 1). The parser at `new_experiments.py:857-863` builds `lower_to_actual` from `ExperimentalConditions.__table__.columns`, so `serum_vial_size_ml` (any case) maps to `serum_vial_size_mL` with **no parser edit**. **Do not edit anything under `backend/services/bulk_uploads/`.**
- Produces: the template column `serum_vial_size_mL` on the `conditions` sheet.

The parser and replicate tests are **pinning tests**. They pass as soon as Task 1 lands, since the behavior comes from generic column loops. Run them to confirm they pass. If one fails, stop and escalate (CLAUDE.md §7: any parser modification needs sign-off). Don't patch the parser.

- [ ] **Step 1: Write the failing template test**

Insert in `tests/api/test_bulk_uploads.py` after `test_new_experiments_template_additives_sheet_headers`:

```python
def test_new_experiments_template_conditions_sheet_headers(client):
    """conditions sheet carries serum_vial_size_mL, the HPHT example row stays
    aligned (blank under the new column, later columns not shifted), and the
    INSTRUCTIONS sheet documents it."""
    import openpyxl, io as _io
    resp = client.get("/api/bulk-uploads/templates/new-experiments")
    assert resp.status_code == 200
    wb = openpyxl.load_workbook(_io.BytesIO(resp.content))
    ws = next((s for s in wb.worksheets if s.title.lower() == "conditions"), None)
    assert ws is not None, "Sheet 'conditions' not found in template"
    raw = [c.value for c in ws[1]]
    headers = [str(v).replace("*", "").split("(")[0].strip() for v in raw if v]
    for required in ("experiment_id", "experiment_type", "water_volume_mL",
                     "feedstock", "serum_vial_size_mL", "initial_conductivity_mS_cm"):
        assert required in headers, f"Missing column '{required}' in conditions sheet"

    example = {h: ws.cell(row=2, column=i + 1).value for i, h in enumerate(headers)}
    assert example["experiment_type"] == "HPHT"
    assert example["feedstock"] == "Nitrogen"
    assert example["serum_vial_size_mL"] is None
    assert example["initial_conductivity_mS_cm"] is None
    assert ws.cell(row=2, column=len(headers) + 1).value is None, "example row longer than headers"

    inst = next(s for s in wb.worksheets if s.title.upper() == "INSTRUCTIONS")
    notes = {r[0].value: r[1].value for r in inst.iter_rows(min_row=1) if r[0].value}
    assert "serum_vial_size_mL" in notes
    assert "Serum experiments only" in notes["serum_vial_size_mL"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/pytest tests/api/test_bulk_uploads.py -v -k conditions_sheet_headers`
Expected: FAIL with `Missing column 'serum_vial_size_mL' in conditions sheet`.

- [ ] **Step 3: Update the template**

In `backend/api/routers/bulk_uploads.py`, conditions `_write_sheet` call: insert `"serum_vial_size_mL",` between `"feedstock",` and `"initial_conductivity_mS_cm",` in `headers`, and change `example_row` to:

```python
            example_row=[
                "HPHT_001", "HPHT", 200.0, 7.0, 5.0, 50.0, 3, 300,
                100.0, 1450.0, "< 150 μm", "Nitrogen", None, None, None, None, None, None,
            ],
```

(The added `None` sits under `serum_vial_size_mL`, so the five original trailing `None`s still line up with the conductivity…alkalinity columns.)

In the `instructions` list, after `("feedstock", "Nitrogen, Nitrate, or Blank."),` add:

```python
            ("serum_vial_size_mL", "Serum experiments only. Nominal vial size in whole mL (e.g. 20, 60, 120, 160). Leave blank for other types."),
```

- [ ] **Step 4: Run the template tests**

Run: `.venv/Scripts/pytest tests/api/test_bulk_uploads.py -v -k new_experiments_template`
Expected: all 4 `new_experiments_template` tests pass.

- [ ] **Step 5: Write the parser pinning tests**

Append to `tests/services/bulk_uploads/test_new_experiments.py`:

```python
# --- serum_vial_size_mL pass-through (docs/issues/issue-serum_vial_size.md.txt) ---
# The parser maps conditions columns from the model, so these pin behavior that
# needs no parser change. If one fails, escalate -- do not edit the locked parser.


def _vial_of(db: Session, experiment_id: str):
    db.flush()
    db.expire_all()
    exp = db.query(Experiment).filter_by(experiment_id=experiment_id).one()
    return exp.conditions.serum_vial_size_mL if exp.conditions else "NO CONDITIONS ROW"


def test_conditions_sheet_stores_serum_vial_size_as_int(db_session: Session):
    """The blank second row forces pandas to read the column as float64, so the
    first value arrives as 120.0 -- it must still land as integer 120."""
    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [
                ["SERUM_9761", None, None, None, None, "ONGOING", None, False],
                ["SERUM_9762", None, None, None, None, "ONGOING", None, False],
            ],
        ),
        "conditions": (
            ["experiment_id", "experiment_type", "serum_vial_size_mL"],
            [["SERUM_9761", "Serum", 120], ["SERUM_9762", "Serum", None]],
        ),
    })
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )
    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 2

    value = _vial_of(db_session, "SERUM_9761")
    assert value == 120 and type(value) is int
    assert _vial_of(db_session, "SERUM_9762") is None


def test_conditions_sheet_vial_size_header_is_case_insensitive(db_session: Session):
    xlsx = make_excel_multisheet({
        "experiments": (
            _EXP_HEADERS,
            [["SERUM_9763", None, None, None, None, "ONGOING", None, False]],
        ),
        "conditions": (
            ["experiment_id", "experiment_type", "Serum_Vial_Size_ML"],
            [["SERUM_9763", "Serum", 60]],
        ),
    })
    *_, errors, _warnings, _info = NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    assert errors == [], f"Unexpected errors: {errors}"
    assert _vial_of(db_session, "SERUM_9763") == 60


def test_sequential_child_inherits_parent_serum_vial_size(db_session: Session):
    """SERUM_9765-2 has no conditions row (no conditions sheet at all), so it can
    only get a vial size via the auto-copy-from-parent branch."""
    parent = _seed_experiment(db_session, "SERUM_9765", 97611, status=ExperimentStatus.COMPLETED)
    db_session.add(ExperimentalConditions(
        experiment_id=parent.experiment_id,
        experiment_fk=parent.id,
        experiment_type="Serum",
        serum_vial_size_mL=160,
    ))
    db_session.flush()

    xlsx = _experiments_excel([
        ["SERUM_9765-2", None, None, None, None, "ONGOING", None, False],
    ])
    created, updated, skipped, errors, warnings, info = (
        NewExperimentsUploadService.bulk_upsert_from_excel(db_session, xlsx)
    )
    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert _vial_of(db_session, "SERUM_9765-2") == 160
```

Append inside `class TestCreateReplicateExperiments` in `tests/test_replicate_creation_service.py`:

```python
    def test_replicates_copy_serum_vial_size(self, test_db):
        parent = _make_parent(test_db, "CRS_VIAL_001", 9850, with_additive=False)
        parent.conditions.serum_vial_size_mL = 120
        test_db.flush()
        created, skipped = create_replicate_experiments(test_db, "CRS_VIAL_001", count=2)
        test_db.flush()
        assert skipped == []
        assert [e.conditions.serum_vial_size_mL for e in created] == [120, 120]
```

- [ ] **Step 6: Run the pinning tests**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/test_new_experiments.py tests/test_replicate_creation_service.py -v`
Expected: all pass, including the 4 new tests. Run each pytest command on its own, never in parallel.

If `test_conditions_sheet_stores_serum_vial_size_as_int` fails, stop and escalate instead of editing the parser. For example: a psycopg2 "can't adapt type numpy.int64" error, or a value that reads back as `120.0` before the expire. Report the exact error and the options: (a) accept as a documented limitation, or (b) an authorized one-line cast in the parser.

- [ ] **Step 7: Commit**

```bash
git add backend/api/routers/bulk_uploads.py tests/api/test_bulk_uploads.py tests/services/bulk_uploads/test_new_experiments.py tests/test_replicate_creation_service.py
git commit -F <scratchpad>/msg_task3.txt
```

```
[feat] Add serum_vial_size_mL to upload template

- conditions sheet header, aligned HPHT example cell, INSTRUCTIONS row
- No parser change: pinning tests cover int storage, mixed-case header,
  sequential auto-copy and replicate copy
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 4: New Experiment wizard

**Files:**
- Modify: `frontend/src/api/conditions.ts:10`
- Modify: `frontend/src/pages/NewExperiment/fieldVisibility.ts:3-14`
- Create: `frontend/src/pages/NewExperiment/vialSize.ts`
- Modify: `frontend/src/pages/NewExperiment/Step2Conditions.tsx`
- Modify: `frontend/src/pages/NewExperiment/index.tsx:26-32,74-92,124-161`
- Test: `frontend/src/pages/NewExperiment/__tests__/vialSize.test.ts` (new), `__tests__/Step2Conditions.test.tsx` (new), `__tests__/Step4Review.test.tsx` (modify)

**Interfaces:**
- Consumes: JSON key `serum_vial_size_mL` on `POST /api/conditions` and `GET /api/conditions/by-experiment/{id}` (Task 2).
- Produces:
  - `ConditionsPayload.serum_vial_size_mL?: number` (also inherited by `ConditionsResponse`). Task 5 uses it.
  - `ConditionField` includes `'serum_vial_size_mL'`.
  - `vialSize.ts`: `VIAL_SIZE_ERROR: string`, `parseVialSize(raw: string): ParsedVialSize`, `vialSizeForPayload(type: ExperimentType | '', raw: string): number | undefined` (throws `Error` on an invalid Serum value), and `type ParsedVialSize = { value?: number; error?: string }`.
  - `Step2Data.serum_vial_size_mL: string`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/pages/NewExperiment/__tests__/vialSize.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { parseVialSize, vialSizeForPayload, VIAL_SIZE_ERROR } from '../vialSize'

describe('parseVialSize', () => {
  it('treats blank and whitespace as no value, no error', () => {
    expect(parseVialSize('')).toEqual({})
    expect(parseVialSize('   ')).toEqual({})
  })

  it('accepts positive whole numbers', () => {
    expect(parseVialSize('120')).toEqual({ value: 120 })
    expect(parseVialSize(' 20 ')).toEqual({ value: 20 })
  })

  it.each(['0', '-1', '120.5', '120.0', '1e2', 'abc'])('rejects %s', (raw) => {
    expect(parseVialSize(raw)).toEqual({ error: VIAL_SIZE_ERROR })
  })
})

describe('vialSizeForPayload', () => {
  it('returns the integer for Serum', () => {
    expect(vialSizeForPayload('Serum', '160')).toBe(160)
  })

  it('returns undefined for blank Serum', () => {
    expect(vialSizeForPayload('Serum', '')).toBeUndefined()
  })

  it('drops a stale hidden value for non-Serum types', () => {
    expect(vialSizeForPayload('HPHT', '120')).toBeUndefined()
    expect(vialSizeForPayload('HPHT', '120.5')).toBeUndefined()
    expect(vialSizeForPayload('', '120')).toBeUndefined()
  })

  it('throws for an invalid Serum value so no experiment is created', () => {
    expect(() => vialSizeForPayload('Serum', '0')).toThrow(VIAL_SIZE_ERROR)
  })
})
```

`'120.0'` is rejected on purpose. The wizard is strict, and the API's `120.0 → 120` coercion only serves non-UI clients.

Create `frontend/src/pages/NewExperiment/__tests__/Step2Conditions.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { Step2Conditions, type Step2Data } from '../Step2Conditions'
import type { ExperimentType } from '../fieldVisibility'
import { VIAL_SIZE_ERROR } from '../vialSize'

const empty: Step2Data = {
  temperature_c: '', initial_ph: '', rock_mass_g: '', water_volume_mL: '',
  serum_vial_size_mL: '',
  particle_size: '', feedstock: '', reactor_number: '', stir_speed_rpm: '',
  initial_conductivity_mS_cm: '', room_temp_pressure_psi: '', rxn_temp_pressure_psi: '',
  co2_partial_pressure_MPa: '', core_height_cm: '', core_width_cm: '',
  confining_pressure: '', pore_pressure: '',
}

function renderStep2(type: ExperimentType | '', patch: Partial<Step2Data> = {}, onChange = vi.fn()) {
  const onNext = vi.fn()
  render(
    <Step2Conditions
      data={{ ...empty, ...patch }}
      experimentType={type}
      onChange={onChange}
      onBack={vi.fn()}
      onNext={onNext}
    />,
  )
  return { onNext, onChange, next: screen.getByRole('button', { name: /next: additives/i }) }
}

describe('Step2Conditions — serum vial size', () => {
  it('shows the field for Serum', () => {
    renderStep2('Serum')
    expect(screen.getByLabelText('Serum Vial Size (mL)')).toBeInTheDocument()
  })

  it.each<ExperimentType>(['HPHT', 'Autoclave', 'Core Flood'])('hides the field for %s', (type) => {
    renderStep2(type)
    expect(screen.queryByLabelText('Serum Vial Size (mL)')).not.toBeInTheDocument()
  })

  it('reports edits through onChange', () => {
    const { onChange } = renderStep2('Serum')
    fireEvent.change(screen.getByLabelText('Serum Vial Size (mL)'), { target: { value: '60' } })
    expect(onChange).toHaveBeenCalledWith({ serum_vial_size_mL: '60' })
  })

  it.each(['0', '-1', '120.5'])('blocks Next with an inline error for %s', (bad) => {
    const { next, onNext } = renderStep2('Serum', { serum_vial_size_mL: bad })
    expect(screen.getByText(VIAL_SIZE_ERROR)).toBeInTheDocument()
    expect(next).toBeDisabled()
    fireEvent.click(next)
    expect(onNext).not.toHaveBeenCalled()
  })

  it('allows Next for a valid value and for blank', () => {
    const { next } = renderStep2('Serum', { serum_vial_size_mL: '120' })
    expect(next).toBeEnabled()
    expect(screen.queryByText(VIAL_SIZE_ERROR)).not.toBeInTheDocument()
  })

  it('does not block Next on a hidden invalid value after a type switch', () => {
    const { next } = renderStep2('HPHT', { serum_vial_size_mL: '120.5' })
    expect(next).toBeEnabled()
    expect(screen.queryByText(VIAL_SIZE_ERROR)).not.toBeInTheDocument()
  })
})
```

In `frontend/src/pages/NewExperiment/__tests__/Step4Review.test.tsx`: add `serum_vial_size_mL: '',` after `water_volume_mL: '',` in the `step2` fixture, change `renderStep4(step1: Step1Data)` to `renderStep4(step1: Step1Data, s2: Step2Data = step2)` and pass `step2={s2}`, then append:

```tsx
describe('Step4Review — serum vial size', () => {
  it('lists serum_vial_size_mL for Serum', () => {
    renderStep4(makeStep1({ experimentType: 'Serum' }), { ...step2, serum_vial_size_mL: '120' })
    expect(screen.getByText('serum_vial_size_mL')).toBeInTheDocument()
    expect(screen.getByText('120')).toBeInTheDocument()
  })

  it('does not list it for HPHT', () => {
    renderStep4(makeStep1({ experimentType: 'HPHT' }), { ...step2, serum_vial_size_mL: '120' })
    expect(screen.queryByText('serum_vial_size_mL')).not.toBeInTheDocument()
  })
})
```

Before writing these, check the `kv()` helper at the top of `Step4Review.tsx`. If it hides blank values or renders key and value in one text node, adjust the two `getByText` calls to match how it renders (e.g. `getByText(/serum_vial_size_mL/)`). Keep the assertion intent unchanged.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/NewExperiment`
Expected: FAIL. `vialSize.test.ts` can't resolve `../vialSize`, Step 2 finds no "Serum Vial Size (mL)" label, and Step 4 can't find `serum_vial_size_mL`.

- [ ] **Step 3: Implement**

`frontend/src/api/conditions.ts`: after `water_volume_mL?: number` add

```ts
  serum_vial_size_mL?: number
```

`frontend/src/pages/NewExperiment/fieldVisibility.ts`: change the union's first line to

```ts
  | 'particle_size' | 'initial_ph' | 'rock_mass_g' | 'water_volume_mL' | 'serum_vial_size_mL'
```

and the `Serum` set to

```ts
  Serum: new Set([
    'particle_size', 'initial_ph', 'rock_mass_g', 'water_volume_mL', 'serum_vial_size_mL',
    'temperature_c', 'feedstock', 'stir_speed_rpm', 'initial_conductivity_mS_cm',
  ]),
```

(HPHT, Autoclave and Core Flood stay unchanged.)

Create `frontend/src/pages/NewExperiment/vialSize.ts`:

```ts
import type { ExperimentType } from './fieldVisibility'

/** Nominal serum vial size (whole mL). Strict on purpose: the wizard creates the
 *  experiment before its conditions, so a value the API would 422 must be caught
 *  here or the experiment is left with no conditions row. */
export const VIAL_SIZE_ERROR = 'Enter a whole number of mL greater than 0'

export type ParsedVialSize = { value?: number; error?: string }

export function parseVialSize(raw: string): ParsedVialSize {
  const s = raw.trim()
  if (s === '') return {}
  if (!/^\d+$/.test(s)) return { error: VIAL_SIZE_ERROR }
  const n = Number(s)
  return n > 0 ? { value: n } : { error: VIAL_SIZE_ERROR }
}

/** The value to send on conditions create. Serum only: a value left in state
 *  after switching to another type is hidden, so it is dropped, not sent.
 *  Throws on an invalid Serum value so the caller aborts before creating anything. */
export function vialSizeForPayload(type: ExperimentType | '', raw: string): number | undefined {
  if (type !== 'Serum') return undefined
  const { value, error } = parseVialSize(raw)
  if (error) throw new Error(`Serum vial size: ${error}`)
  return value
}
```

`frontend/src/pages/NewExperiment/Step2Conditions.tsx`:
- Imports: add `import { parseVialSize } from './vialSize'`.
- `Step2Data`: add `serum_vial_size_mL: string` after `water_volume_mL: string`.
- In the component body, after the `wtr` computation:

```tsx
  // The field() helper can't carry step/min/error, so this input is rendered directly.
  const vialVisible = isVisible('serum_vial_size_mL', experimentType)
  const vialError = vialVisible ? parseVialSize(data.serum_vial_size_mL).error : undefined
```

- After the Water Volume line (`{field('Water Volume', ...)}`):

```tsx
        {vialVisible && (
          <Input
            key="serum_vial_size_mL"
            label="Serum Vial Size (mL)"
            type="number"
            step={1}
            min={1}
            value={data.serum_vial_size_mL}
            error={vialError}
            onChange={(e) => onChange({ serum_vial_size_mL: e.target.value })}
          />
        )}
```

- The Next button: `<Button variant="primary" onClick={onNext} disabled={!!vialError}>Next: Additives →</Button>`

`frontend/src/pages/NewExperiment/index.tsx`:
- Import: `import { vialSizeForPayload } from './vialSize'`.
- `defaultStep2`: `temperature_c: '', initial_ph: '', rock_mass_g: '', water_volume_mL: '', serum_vial_size_mL: '',`
- Copy-from block: after `water_volume_mL: numToStr(conditions.water_volume_mL),` add `serum_vial_size_mL: numToStr(conditions.serum_vial_size_mL),`
- First lines of `mutationFn`, **before** `experimentsApi.create`:

```ts
      // Validate before creating anything: the experiment is created before its
      // conditions, so a late 422 would strand an experiment with no conditions row.
      const serumVialSize = vialSizeForPayload(step1.experimentType, step2.serum_vial_size_mL)
```

- In `conditionsApi.create({...})`, after `water_volume_mL: toFloat(step2.water_volume_mL),` add `serum_vial_size_mL: serumVialSize,`. Do **not** use `parseInt` (line 151's `reactor_number` idiom truncates `120.5` to `120`).

- [ ] **Step 4: Run tests, lint, type-check**

Run: `cd frontend && npx vitest run src/pages/NewExperiment && npm run lint && npx tsc --noEmit -p .`
Expected: all NewExperiment tests pass, and lint is clean for the touched files. `tsc` must add no new errors in the touched files. The pre-existing baseline is 3 errors in `ResultsTab.columns.test.tsx` (issue #106); compare against `develop` if the count differs.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/conditions.ts frontend/src/pages/NewExperiment/
git commit -F <scratchpad>/msg_task4.txt
```

```
[feat] Add serum vial size to New Experiment wizard

- Serum-only Step 2 input with inline error; Next blocked on invalid
- Strict integer parse; hidden value dropped for non-Serum types
- Copy-from carries the value; Step 4 review lists it
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 5: Conditions tab read view and edit modal

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx:165-185,237,322`
- Test: `frontend/src/pages/ExperimentDetail/__tests__/ConditionsTab.buttons.test.tsx` (append)

**Interfaces:**
- Consumes: `ConditionsPayload.serum_vial_size_mL?: number` (Task 4), API field (Task 2).
- Produces: nothing used by later tasks.

- [ ] **Step 1: Write the failing tests**

Append to `ConditionsTab.buttons.test.tsx` (it already has `wrap`, `mockConditions`, `userEvent`):

```tsx
describe('ConditionsTab — serum vial size', () => {
  const serum = { ...mockConditions, experiment_type: 'Serum', serum_vial_size_mL: 120 }

  it('shows the read row when set', () => {
    wrap(<ConditionsTab conditions={serum} experimentId="SERUM_001" experimentFk={1} />)
    expect(screen.getByText('Serum Vial Size')).toBeInTheDocument()
    expect(screen.getByText('120 mL')).toBeInTheDocument()
  })

  it('shows no read row when null', () => {
    wrap(<ConditionsTab conditions={{ ...serum, serum_vial_size_mL: null }} experimentId="SERUM_001" experimentFk={1} />)
    expect(screen.queryByText('Serum Vial Size')).not.toBeInTheDocument()
  })

  async function openEditModal() {
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }))
  }

  it('edit modal shows the input for Serum, seeded with the stored value', async () => {
    wrap(<ConditionsTab conditions={serum} experimentId="SERUM_001" experimentFk={1} />)
    await openEditModal()
    expect(screen.getByLabelText('Serum Vial Size (mL)')).toHaveValue(120)
  })

  it('edit modal shows the input for a Serum with no stored value', async () => {
    wrap(<ConditionsTab conditions={{ ...serum, serum_vial_size_mL: null }} experimentId="SERUM_001" experimentFk={1} />)
    await openEditModal()
    expect(screen.getByLabelText('Serum Vial Size (mL)')).toHaveValue(null)
  })

  it('edit modal hides the input for HPHT with no stored value', async () => {
    wrap(<ConditionsTab conditions={mockConditions} experimentId="HPHT_001" experimentFk={1} />)
    await openEditModal()
    expect(screen.queryByLabelText('Serum Vial Size (mL)')).not.toBeInTheDocument()
  })

  it('edit modal shows the input for HPHT when a value is already stored', async () => {
    wrap(<ConditionsTab conditions={{ ...mockConditions, serum_vial_size_mL: 60 }} experimentId="HPHT_001" experimentFk={1} />)
    await openEditModal()
    expect(screen.getByLabelText('Serum Vial Size (mL)')).toHaveValue(60)
  })

  it('keeps the input visible while the user clears a stored value', async () => {
    wrap(<ConditionsTab conditions={{ ...mockConditions, serum_vial_size_mL: 60 }} experimentId="HPHT_001" experimentFk={1} />)
    await openEditModal()
    await userEvent.clear(screen.getByLabelText('Serum Vial Size (mL)'))
    expect(screen.getByLabelText('Serum Vial Size (mL)')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/ExperimentDetail/__tests__/ConditionsTab.buttons.test.tsx`
Expected: FAIL. The new tests find no "Serum Vial Size" text or label, and the existing tests still pass.

- [ ] **Step 3: Implement**

In `ConditionsTab.tsx`:

Read view, after `<Row label="Water Volume" value={conditions.water_volume_mL} unit="mL" />`:

```tsx
        <Row label="Serum Vial Size" value={conditions.serum_vial_size_mL} unit="mL" />
```

`openEdit`, after `water_volume_mL: conditions?.water_volume_mL ?? undefined,`:

```tsx
      serum_vial_size_mL: conditions?.serum_vial_size_mL ?? undefined,
```

Edit modal, after the `Water Volume (mL)` input:

```tsx
            {/* First type-conditional field in this modal. Keyed on the STORED value
                (not form) so the input does not vanish while the user clears it. */}
            {(form.experiment_type === 'Serum' || conditions?.serum_vial_size_mL != null) && (
              <Input label="Serum Vial Size (mL)" type="number" step={1} min={1} value={form.serum_vial_size_mL ?? ''} onChange={set('serum_vial_size_mL')} />
            )}
```

Invalid values (`0`, `-1`, `120.5`) are sent as numbers and rejected by the API. The existing "Update failed" toast shows the 422, and PATCH is a single request, so nothing is half-written. Clearing the field doesn't clear the stored value: that's a known pre-existing bug for every field in this modal (spec Notes) and out of scope here.

- [ ] **Step 4: Run tests, lint**

Run: `cd frontend && npx vitest run src/pages/ExperimentDetail && npm run lint`
Expected: all ExperimentDetail tests pass; lint clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/ConditionsTab.tsx frontend/src/pages/ExperimentDetail/__tests__/ConditionsTab.buttons.test.tsx
git commit -F <scratchpad>/msg_task5.txt
```

```
[feat] Show serum vial size on Conditions tab

- Read row (hidden when null) and edit input for Serum, or when a
  value is already stored
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 6: Docs, full verification, live check

**Files:**
- Modify: `.claude/rules/MODELS.md` (ExperimentalConditions key fields), `docs/POWERBI_MODEL.md:17`, `docs/upload_templates/new_experiments.md:16`, `docs/api/API_REFERENCE.md` (Conditions section), `docs/working/issue-log.md` (append)

**Interfaces:** none.

- [ ] **Step 1: Update docs (use the Edit tool so the sync hook fires)**

`.claude/rules/MODELS.md`: in `ExperimentalConditions` → **Key Fields**, after the `temperature_c, initial_ph, rock_mass_g, water_volume_mL` bullet, add:

```markdown
  - `serum_vial_size_mL` (Integer, nullable; added 2026-10-19, Alembic `e9a4c1f7b3d2`): the **nominal** serum vial size in whole mL (20, 60, 120, 160, ...). **Tracking only** — no calculation reads it. **Not the true total vial volume:** a "120 mL" vial holds noticeably more when filled to the brim, so a future headspace calc (total volume − liquid volume) needs a lookup by nominal size or a measured column, not this value. "Serum only" is enforced in the UI only (wizard Step 2 shows it for Serum; the Conditions edit modal shows it for Serum or when a value is already stored); the API and the new-experiments bulk upload accept it on any type. Positive-integer validation lives in `ConditionsCreate`/`ConditionsUpdate` (`gt=0`, 422 for `0`, `-1`, `120.5`) and the UI — there is deliberately **no DB `CHECK`**, because the conditions-sheet loop in `new_experiments.py` has no per-row SAVEPOINT and a constraint violation would break every remaining row. The bulk parser applies no validation to it (same as `reactor_number`). Raw SQL must quote it: `ec."serum_vial_size_mL"`. Exposed in `v_experiment_conditions` (not `v_experiments`). Existing rows are NULL; no backfill.
```

`docs/POWERBI_MODEL.md`: in the `v_experiment_conditions` row, insert `` `serum_vial_size_mL`, `` after `` `water_volume_mL`, ``.

`docs/upload_templates/new_experiments.md`: change the `conditions` row's Columns cell to
`experiment_id*, columns matching ExperimentalConditions (e.g., particle_size, rock_mass_g, water_volume_mL, reactor_number, serum_vial_size_mL — Serum only, nominal whole mL, blank for other types)`.

`docs/api/API_REFERENCE.md`: after the `reactor_slot` paragraph in `## Conditions`, add:

```markdown
**`serum_vial_size_mL`** (integer, nullable) is accepted on `ConditionsCreate` and `ConditionsUpdate` and returned on `ConditionsResponse`. It is the nominal serum vial size in whole mL. It must be a positive integer: `0`, `-1` and `120.5` return **422** (Pydantic `gt=0` on `Optional[int]`); `120.0` is coerced to `120`. It is accepted for **any** `experiment_type` — "Serum only" is a UI rule, unlike `reactor_number`'s 422 check. A rejected PATCH writes nothing. No derived field reads it.
```

- [ ] **Step 2: Confirm the docs sync ran**

Run: `git status --short docs/project_context/`
Expected: `POWERBI_MODEL.md`, `new_experiments.md` and `API_REFERENCE.md` copies show as modified. If one doesn't (an edit went through Bash/python), run the hook's full sync: `.venv/Scripts/python .claude/hooks/sync_docs_to_project_context.py` (check the script for its full-sync entry point, `full_sync()`).

- [ ] **Step 3: Full backend verification (one process, nothing else running)**

Run: `.venv/Scripts/pytest tests/services/ tests/regression/ tests/api/ tests/views/ tests/models/ -v`
then: `.venv/Scripts/pytest tests/test_replicate_creation_service.py -v`
Expected: 0 failures. If a failure appears in a file this branch didn't touch, re-run that file alone and check it on `develop` before calling it a regression (known `pg_backup_restore` order fragility).

- [ ] **Step 4: Full frontend verification**

Run: `cd frontend && npm run test && npm run lint && npm run build`
Expected: all vitest files pass, lint has 0 warnings, and the build succeeds.

- [ ] **Step 5: Scope guard**

Run: `git diff --stat develop -- backend/services/bulk_uploads/ database/models/enums.py auth/ && git diff --name-only --diff-filter=M develop -- alembic/versions/ && git diff --name-only develop -- database/models/ && git diff --name-only develop -- frontend/package.json frontend/package-lock.json`
Expected: the first, second and fourth outputs are empty, and the third lists only `database/models/conditions.py`.

- [ ] **Step 6: Upgrade the dev DB and do the live check**

```bash
DATABASE_URL=postgresql://experiments_user:password@localhost:5432/experiments .venv/Scripts/alembic current
```

Expected `b8c4e2d7f9a1`. If it isn't, stop and report the stamp; don't upgrade a DB stamped on another branch. Then `alembic upgrade head` and confirm `SELECT count(*) FROM experimental_conditions WHERE "serum_vial_size_mL" IS NOT NULL` = 0 and `SELECT experiment_id, "serum_vial_size_mL" FROM v_experiment_conditions LIMIT 1` runs.

Restart the dev backend on this branch. First check `netstat -ano | findstr :8000` shows one listener; kill any orphaned `spawn_main` worker. Then, via the run skill / Chrome DevTools at `http://localhost:5173`:
1. New Experiment → type Serum → Step 2 shows "Serum Vial Size (mL)". Enter `120.5` and confirm the inline error appears and Next is disabled. Enter `120`, then Next → Step 4 lists `serum_vial_size_mL 120` → Create.
2. The new experiment's Conditions tab shows "Serum Vial Size 120 mL". Edit → change to 160 → Save → 160. Edit → `0` → Save gives the "Update failed" toast and the value stays 160.
3. New Experiment → type HPHT: no vial field.
4. Download the new-experiments template: the conditions sheet has `serum_vial_size_mL`.
5. No console errors. Delete the test experiment afterwards.

- [ ] **Step 7: Issue-log entry**

Append a `## 2026-10-19 | Serum vial size — add serum_vial_size_mL to conditions (\`feat/serum-vial-size\`)` entry to `docs/working/issue-log.md` in the house format (Files changed, Why, Migration rehearsal result, Dev DB before/after, Verification counts with the HEAD hash, DevTools check, Deploy note, Follow-ups, Tests added / Docs updated). Use the real numbers from Steps 3–6. Deploy note: nightly `alembic upgrade head` adds the column and recreates the view before the service restarts, and refreshing Power BI shows the new column. Follow-ups:
  (a) the Conditions edit modal can't clear any field (`set()` → `undefined` → dropped by `exclude_unset`), which deserves its own issue;
  (b) the bulk parser doesn't validate the column (a fractional cell is silently rounded by Postgres, a non-numeric cell breaks the rest of the sheet), which already applies to every numeric conditions column;
  (c) Step 4 review labels conditions by raw key.

- [ ] **Step 8: Commit**

```bash
git add .claude/rules/MODELS.md docs/POWERBI_MODEL.md docs/upload_templates/new_experiments.md docs/api/API_REFERENCE.md docs/project_context/ docs/working/issue-log.md
git commit -F <scratchpad>/msg_task6.txt
```

```
[feat] Document serum_vial_size_mL

- MODELS.md (nominal, tracking only, UI-only Serum scope, no CHECK),
  POWERBI_MODEL.md, upload template doc, API reference, issue log
- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

Then run `/complete-task`. Open the PR with `gh pr create --base develop`, and end the body with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
