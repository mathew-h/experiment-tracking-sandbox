# feature: model reactors as a real entity — one source of truth for slots, specs, and out-of-service state

> **Verified against** `OneDrive - Addis Energy/Documents/01_Software/database_sandbox/experiment_tracking_sandbox`, branch `feat/issue-85-dashboard-kpi-cards` @ `49e5f8f`. `dashboard.py` and `schemas/dashboard.py` citations are **post-#85**; every other file cited is identical on `develop`.

**Sequencing: this is the follow-up to `issue-reactor-slot-identity-and-occupancy-uniqueness.md` and explicitly supersedes the `reactor_slot` discriminator column that ticket adds.** Do not start this until that ticket has shipped and the auto-completion bug is closed. That one is a live data-corruption fix; this one is structural.

## Summary

A reactor currently exists as three unrelated things: an integer on a conditions row, a Python dict of hardware specs, and a TypeScript record of the same specs. There is no row anywhere in the database representing "reactor R07."

Consequences, roughly in descending order of value once fixed:

1. **Reactor-level state becomes expressible.** Today "empty" and "out of service for maintenance" render identically on the dashboard. This is probably the most useful capability the lab is currently missing, and it is not achievable at all without an entity to hang the state on.
2. **`reactor_number` becomes a real FK**, which dissolves the R01/CF01 collision structurally rather than patching it — `R01` and `CF01` are just different rows with different primary keys, and the type discriminator stops being load-bearing.
3. **Specs get queried instead of duplicated** across two languages.
4. **"Empty" becomes queryable** rather than computed by set subtraction in the frontend.
5. **Adding `CF03`, or a seventeenth vessel, becomes a data insert** instead of a coordinated edit across three files.

---

## Background: the current three sources of truth

**Backend spec table** — `backend/api/routers/dashboard.py:24-41`, `dict[int, dict[str, object]]` keyed by bare integer, keys 1–16, values `volume_mL` / `material` / `vendor`.

Because it's keyed by the bare integer and only covers the HPHT vessels, it needs an explicit guard so Core Flood rigs don't inherit R01/R02's specs — `dashboard.py:168-171`:

```python
        # REACTOR_SPECS is keyed by bare reactor_number and only covers the R01-R16
        # HPHT vessels. Core Flood reactors reuse the same 1/2 numbering (CF01/CF02),
        # so this must be skipped for CF or it silently inherits R01/R02's HPHT spec.
        specs = REACTOR_SPECS.get(rn, {}) if not is_cf else {}
```

**Frontend spec table** — `frontend/src/pages/ReactorGrid.tsx:19-38`, `Record<string, {...}>` keyed by *label string* (`R01`–`R16`, no `CF*` entries). Same data, different key type, maintained by hand:

```ts
// Static hardware specs — used for both occupied and empty slots.
// Source: lab hardware inventory (issue #2).
const REACTOR_SPECS: Record<string, { volume_mL: number; material: string; vendor: string }> = {
  R01: { volume_mL: 100, material: 'Hastelloy', vendor: 'Yushen' },
  ...
```

Used as a fallback at lines 242-244 and 253-255: `card!.volume_mL ?? REACTOR_SPECS[label]?.volume_mL ?? null`.

**Frontend slot inventory** — `frontend/src/pages/ReactorGrid.tsx:13-14`, used at `:581`:

```ts
const R_SLOTS = Array.from({ length: 16 }, (_, i) => `R${String(i + 1).padStart(2, '0')}`)
const CF_SLOTS = ['CF01', 'CF02']
```

**Backend slot inventory** — new in #85, `dashboard.py:44-45`:

```python
R_SLOT_COUNT = 16    # HPHT vessels R01-R16; must stay in sync with REACTOR_SPECS
CF_SLOT_COUNT = 3    # Core flood rigs CF01-CF03
```

So the *count* of physical slots is hardcoded in two languages, the *specs* are hardcoded in two languages with different key types, and the CF slots have no spec entry at all.

**And the two counts already disagree.** `CF_SLOT_COUNT = 3` versus `CF_SLOTS = ['CF01', 'CF02']`. `_occupancy(cards, "CF", 3)` will report `total: 3` while the grid renders two cards, so a real CF03 experiment resolves to a card the grid has no slot for. This is exactly the failure mode this ticket exists to prevent, and it appeared within one commit of the constant being introduced — which is the whole argument in miniature. Worth fixing on the #85 branch immediately (a one-line frontend change) rather than waiting for this ticket; the comment in `_occupancy`'s own docstring is a self-aware acknowledgment that nothing constrains these values.

The `R_SLOT_COUNT` / `CF_SLOT_COUNT` pair is the patch `issue-dashboard-kpi-overhaul.md` described as reducing three sources of truth to one. It is a reasonable patch, and it did reduce the backend to one place, but it does not make the slot inventory *data*, and the `# must stay in sync with` comment is doing the work a foreign key should do.

---

## Proposed Changes

### 1. The `reactors` table

Starting point for discussion, not a settled schema:

```python
class Reactor(Base):
    __tablename__ = "reactors"

    id            = Column(Integer, primary_key=True)
    label         = Column(String(8), nullable=False, unique=True)   # 'R01' … 'R16', 'CF01', 'CF02'
    series        = Column(String(8), nullable=False)                # 'HPHT' | 'CF'  (CHECK-constrained)
    number        = Column(Integer, nullable=False)                  # 1..16 within series
    volume_ml     = Column(Float, nullable=True)
    material      = Column(String, nullable=True)
    vendor        = Column(String, nullable=True)
    state         = Column(String, nullable=False, server_default="AVAILABLE")
    state_note    = Column(Text, nullable=True)
    commissioned_on   = Column(Date, nullable=True)
    decommissioned_on = Column(Date, nullable=True)

    __table_args__ = (
        UniqueConstraint("series", "number"),
        CheckConstraint("series IN ('HPHT','CF')"),
        CheckConstraint("state IN ('AVAILABLE','MAINTENANCE','OUT_OF_SERVICE')"),
    )
```

**Open questions for the team, all of which change the schema:**

- **What are the actual reactor states the lab needs?** I've guessed `AVAILABLE` / `MAINTENANCE` / `OUT_OF_SERVICE`. The lab may want more granularity (leak-testing, awaiting-part, in-cleaning) or fewer. This is the single most valuable field in the table and it should be named by whoever runs the rigs, not inferred from the code. **Ask before implementing.**
- **Does reactor state need history, or is current-state enough?** A `state` column answers "what's the status now." A `reactor_state_events` child table answers "how much downtime did R07 have last quarter," which is a plausible thing to want and a much bigger ticket. Recommend current-state only for this pass, with the `state_note` free-text field as the escape hatch, and treat history as a separate ticket if it's actually wanted.
- **Do the CF rigs have specs worth recording?** Neither existing spec table has `CF01`/`CF02` entries. If they do, this migration is the moment to capture them; if they genuinely don't, the columns are just nullable.
- **Is 16 + 3 correct?** #85 says three CF rigs, the frontend says two. Resolve that before writing the backfill (it decides whether you seed 18 or 19 rows), and confirm whether any of the 16 HPHT vessels are currently decommissioned — that's exactly the state this table is meant to represent, so it would be good to seed it truthfully rather than marking everything `AVAILABLE`.
- **Where does the seed data live?** An Alembic data migration is the obvious answer, but it means hardware inventory lives in a migration file forever. Alternative: a small idempotent seed script under `database/` that the migration calls. Slight preference for the latter, since the lab will edit this data again.

### 2. Repoint `experimental_conditions`

Add `reactor_id = Column(Integer, ForeignKey("reactors.id"), nullable=True)`.

Backfill from `reactor_slot` (added by the previous ticket) — that column's values map 1:1 onto `reactors.label`, which is precisely why the previous ticket uses a label string rather than a series enum. The backfill is a single join.

**Column removal — recommend deferring, not doing it here.** Both `reactor_number` and `reactor_slot` should eventually go, but:

- `reactor_number` is read by the Power BI flattened SQL views, by `database/event_listeners.py:119,151` (the audit snapshot column list), by `database/data_migrations/swap_reactor_4_7_015.py`, and by the `GET /api/experiments?reactor_number=` list filter (`backend/api/routers/experiments.py:132-135`, tested by `test_list_experiments_type_reactor_filter_pagination_regression` at `tests/api/test_experiments.py:295`). The Power BI dependency is the blocking one — dropping the column breaks reports outside this repo, with no compile error to warn you. **Confirm the view definitions and any Power BI-side queries before dropping anything.**
- Recommended path: land `reactor_id` alongside both existing columns, migrate all read sites to `reactor_id`, ship, verify Power BI, *then* drop in a follow-up migration. Three small safe steps instead of one large risky one.

### 3. The uniqueness constraint becomes trivial

The previous ticket has to enforce one-ONGOING-per-slot with a trigger, because `Experiment.status` and `experimental_conditions.reactor_slot` live on different tables and Postgres partial unique indexes are single-table.

With a `reactors` FK the same problem exists structurally — but the natural expression changes. Two options:

- **Keep the trigger**, just repointed at `reactor_id`. Smallest diff from the previous ticket.
- **Move occupancy onto `reactors`** as a nullable `current_experiment_fk` FK with a unique constraint, maintained on ONGOING transitions. This makes "who is in R07" a single-row read, makes "which slots are empty" a plain `WHERE current_experiment_fk IS NULL` (item 4 of the summary), and gets uniqueness from an ordinary unique index with no trigger. Cost: a second thing to keep in sync with `Experiment.status`, which is the failure mode this whole pair of tickets is about.

Lean toward the first for safety, but the second is genuinely tempting and worth arguing about in the PR. Whichever you pick, the trigger or constraint from the previous ticket must be replaced, not left in place alongside — two overlapping enforcement mechanisms is worse than either alone.

### 4. Call sites to rewrite

| File | Line(s) | Change |
|---|---|---|
| `backend/api/routers/dashboard.py` | 25-41 | Delete `REACTOR_SPECS`; join `reactors` |
| `backend/api/routers/dashboard.py` | 44-45 | Delete `R_SLOT_COUNT` / `CF_SLOT_COUNT`; `total` comes from `SELECT count(*) FROM reactors WHERE series = …` |
| `backend/api/routers/dashboard.py` | 48-63 | `_occupancy()` takes the reactor rows instead of a prefix + hardcoded total; "empty" becomes a left-join miss rather than arithmetic |
| `backend/api/routers/dashboard.py` | 96-165 | Reactor cards join `reactors`; label and specs come from the row; the dedup on derived labels (126-140) goes away, since the constraint guarantees one occupant |
| `backend/api/routers/dashboard.py` | 144-147 | Delete the CF-inherits-R-specs guard and its comment |
| `backend/api/routers/dashboard.py` | 317-350 | `GET /reactor-status` — same treatment |
| `backend/api/routers/conditions.py` | 16-25, 63, 87 | `_validate_reactor_number` becomes an FK existence check plus a `series`-vs-`experiment_type` consistency check |
| `backend/api/routers/experiments.py` | 132-135 | `?reactor_number=` filter — decide whether to keep it, add `?reactor=R01`, or both |
| `backend/services/bulk_uploads/experiment_status.py` | 196-197, 219-228, 244-251, 383-390 | Occupancy keyed on `reactor_id` |
| `backend/services/bulk_uploads/new_experiments.py` | 599-610, 673-681 | Same |
| `backend/services/notion_sync/import_.py` | 44-67 | Label → `reactors.label` lookup; the `CF`/`R` prefix parsing disappears |
| `backend/services/notion_sync/export.py` | 30-41, 74, 82 | `_reactor_label_for` deleted; read `reactor.label` |
| `frontend/src/pages/ReactorGrid.tsx` | 13-14, 19-38, 242-255, 581 | Delete both hardcoded tables; render slots from a new endpoint |
| `frontend/src/components/ui/SlotBar.tsx` | whole file | New in #85. Check whether it derives anything from a hardcoded total. |

### 5. New endpoint

`GET /api/reactors` returning every reactor with specs, state, and current occupant. This is what lets the frontend stop hardcoding the slot inventory. Include empty slots — the frontend should no longer be doing set subtraction to find them.

### 6. Reactor state in the UI

The payoff. An `OUT_OF_SERVICE` or `MAINTENANCE` slot should render visually distinct from an empty one, with the `state_note` surfaced. Also needs a way to *set* the state — probably `PATCH /api/reactors/{label}` plus a control in the reactor pop-out, which already has an editing surface (see `issue-reactor-modification-rename-and-scoping-fix.md` and `issue-reactor-popout-overhaul.md` for the existing patterns there).

**Scope call needed:** this UI work could reasonably be split into its own ticket so the schema change can land and be verified independently. Recommend splitting, and shipping the table plus the read path first.

---

## Verification

- `GET /api/reactors` returns 19 rows (or whatever the confirmed count is — see the 16+3 vs 16+2 question above), each with correct specs.
- `summary.reactors.total` and `summary.core_floods.total` come from the table, and the frontend grid renders exactly that many slots. Add a test that a new `INSERT INTO reactors` row appears in both without a code change — that's the whole point of the ticket, and it's the one assertion the current constant pair cannot satisfy.
- Dashboard reactor grid is byte-identical to `main`'s output for the same data, except that CF slots now show specs if any were recorded. Diff the JSON response before and after — this is the highest-value check in the whole ticket.
- `reactors_in_use` with one ONGOING HPHT in `R01` and one ONGOING CF in `CF01` → 2.
- Every test in `tests/api/test_dashboard.py` passes unchanged, in particular `test_cf01_does_not_inherit_hpht_reactor_1_hardware_specs` (440) and `test_cf_and_hpht_in_same_reactor_number_each_get_own_slot` (542). If either needs modifying to pass, stop and explain why in the PR — those two encode the exact invariants this ticket is supposed to make structural.
- `tests/services/test_notion_sync_import.py:200-265` and `tests/services/test_notion_sync_export.py:139` (`test_export_cf_slots_mapped_correctly`) pass.
- `tests/data_migrations/test_swap_reactor_4_7_015.py` passes — that migration manipulates `reactor_number` directly across ten statements (`swap_reactor_4_7_015.py:68-135`). It's a historical one-shot, so the likely correct answer is to leave it and its test alone against the retained `reactor_number` column, but check that it doesn't now leave `reactor_id` inconsistent if ever re-run.
- `frontend/src/pages/__tests__/ReactorGrid.test.tsx` updated for the endpoint-driven slot list.
- **Power BI:** confirm the flattened views still resolve and that at least one report renders, before the follow-up migration drops `reactor_number`.

---

## Data Model Notes

| Object | Change |
|---|---|
| `reactors` | New table. ~18 seeded rows. |
| `experimental_conditions.reactor_id` | New nullable FK → `reactors.id`. Backfilled from `reactor_slot`. |
| `experimental_conditions.reactor_slot` | Superseded by `reactor_id`. Retained through this ticket; dropped in the follow-up. |
| `experimental_conditions.reactor_number` | Retained. Power BI and audit-log dependency; drop only after confirming those. |
| Occupancy uniqueness | Previous ticket's trigger repointed at `reactor_id`, **or** replaced by `reactors.current_experiment_fk` + unique constraint. Pick one; don't run both. |

Alembic head at time of writing: `daae92e908f1`. Re-check — the previous ticket will have added a revision.

## Cost estimate

A migration backfilling ~18 rows, plus rewriting five `reactor_number ==` comparison sites, the reactor grid, the KPI occupancy logic, and both spec tables. It touches the dashboard, both bulk upload paths, and the Notion sync in both directions. Not large in lines changed, but broad in surface area, and the Power BI coupling means the column-drop step needs care.

## Labels

`enhancement`, `database`, `architecture`, `dashboard`, `blocked`

## Notes

`blocked` until `issue-reactor-slot-identity-and-occupancy-uniqueness.md` ships. The temptation will be to skip that ticket and come straight here, since this is the "real" fix — resist it. The auto-completion bug is mutating experiment records now, and this ticket is at minimum a week of careful work with a Power BI dependency hanging off it.

Also flagging that the team-decision items in §1 are not rhetorical. Reactor state is the highest-value thing this table unlocks, and getting the state vocabulary wrong means either a second migration or a `state_note` column doing work a proper enum should be doing.
