# Add `v_experiment_additive_names_summary` PostgreSQL view

## Summary

Add a new managed view `v_experiment_additive_names_summary` to `database/event_listeners.py` alongside the existing `v_experiment_additives_summary` view. Where the existing view produces a rich summary string (name + amount + unit), this new view aggregates **only compound names** — one comma-separated string per experiment — for use in Power BI reports and filtered SQL queries where the full additive detail is not needed.

## Background

`v_experiment_additives_summary` is currently the only view that surfaces additive data. It produces strings like `"Nickel Chloride 0.5 g; Copper Sulfate 1.2 mmol"`. Downstream Power BI visuals and ad-hoc SQL queries sometimes need only the compound names (e.g., for a slicer filter or a text label column), and parsing the existing summary string is fragile. A dedicated name-only view avoids that coupling.

## Proposed Change

### Location

`database/event_listeners.py` — append a new entry to the `_VIEWS` list, immediately after the `v_experiment_additives_summary` entry.

### View Definition

```sql
CREATE VIEW v_experiment_additive_names_summary AS
SELECT
    e.experiment_id,
    STRING_AGG(c.name, ', ' ORDER BY c.name) AS additive_names
FROM experiments e
LEFT JOIN experimental_conditions ec ON ec.experiment_fk = e.id
LEFT JOIN chemical_additives ca      ON ca.experiment_id = ec.id
LEFT JOIN compounds c                ON c.id = ca.compound_id
GROUP BY e.experiment_id
```

Key decisions:
- Uses `LEFT JOIN` throughout so experiments with no additives still appear in the result with `additive_names = NULL`. This matches the graceful-null requirement and keeps the view consistent with how `v_experiments` handles optional relationships.
- `STRING_AGG(..., ', ' ORDER BY c.name)` produces a stable, alphabetically sorted string (e.g., `"Copper Sulfate, Nickel Chloride"`). `STRING_AGG` returns `NULL` — not an empty string — when all input values are null, which is the correct behavior for no-additive experiments.
- No `COALESCE` wrapper is added by default; consumers can apply `COALESCE(additive_names, '')` if they need an empty string instead.

### List Entry (`_VIEWS`)

```python
("v_experiment_additive_names_summary", """
    CREATE VIEW v_experiment_additive_names_summary AS
    SELECT
        e.experiment_id,
        STRING_AGG(c.name, ', ' ORDER BY c.name) AS additive_names
    FROM experiments e
    LEFT JOIN experimental_conditions ec ON ec.experiment_fk = e.id
    LEFT JOIN chemical_additives ca      ON ca.experiment_id = ec.id
    LEFT JOIN compounds c                ON c.id = ca.compound_id
    GROUP BY e.experiment_id
"""),
```

The existing drop-and-recreate loop in `event_listeners.py` will automatically handle `DROP VIEW IF EXISTS v_experiment_additive_names_summary CASCADE` and recreation on every app start — no additional teardown logic is needed.

## Acceptance Criteria

- [ ] `v_experiment_additive_names_summary` is present in `_VIEWS` in `database/event_listeners.py`.
- [ ] The view returns one row per experiment (verified against experiments table count).
- [ ] Experiments with no additives return `NULL` for `additive_names` (not an error, not a missing row).
- [ ] Experiments with multiple additives return a comma-separated, alphabetically ordered string.
- [ ] App starts cleanly — no view creation errors logged on startup.
- [ ] Power BI can query the view directly (smoke test: `SELECT * FROM v_experiment_additive_names_summary LIMIT 10`).

## Out of Scope

- Changes to the calculation engine or any SQLAlchemy models.
- Modifying `v_experiment_additives_summary` (existing view is unchanged).
- API endpoints — this view is for direct SQL/Power BI consumption only.

## Labels

`backend`, `database`, `enhancement`
