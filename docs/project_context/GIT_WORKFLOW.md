# Git Workflow

## Branch Structure
```
main          ← production-ready only; never commit directly
  └─ develop  ← integration; feature branches merge here first
       ├─ infra/lab-pc-server-setup
       ├─ feature/m1-postgres-migration
       ├─ feature/m2-calculation-engine
       ├─ feature/m3-fastapi-backend
       ├─ feature/m4-react-shell
       ├─ feature/m5-experiment-pages
       ├─ feature/m6-bulk-uploads
       ├─ feature/m7-reactor-dashboard
       └─ feature/m8-testing-docs
```

## Branch Rules
- Create feature branch from `develop`, never from `main`
- One branch per milestone; sub-tasks are commits within that branch
- Feature branch → `develop`: requires agent review + Test Writer Agent pass
- `develop` → `main`: requires explicit user sign-off
- Never force-push to `develop` or `main`
- Delete feature branches after successful merge

## Commit Message Format
```
[M<number>] <imperative short description> (<50 chars max)

- Detail bullet if needed
- Tests added: <yes/no, what kind>
- Docs updated: <yes/no, what>

Refs: #<issue number if applicable>
```

## Pre-Merge Checklist
- [ ] All tests pass (`pytest` backend, `vitest` frontend)
- [ ] No linting errors (`flake8`/`black` backend, `eslint` frontend)
- [ ] No hardcoded secrets, URLs, file paths, or hex color values
- [ ] All new functions have type hints (Python) or TypeScript types
- [ ] All new API endpoints have docstrings
- [ ] No N+1 query patterns introduced
- [ ] Write endpoints call calculation engine where applicable
- [ ] Migration files (if any) have both `upgrade` and `downgrade` implemented
- [ ] `.env.example` updated if new env vars added
- [ ] Calculation events appear in `logs/calculations.log` for any write operations tested
