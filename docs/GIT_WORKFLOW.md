# Git Workflow

## Prerequisites

`develop` must exist **locally and on the remote** before any branch work (all feature, fix, chore, and milestone branches are created from `develop`). If the repository only has `main`:

```bash
git checkout -b develop main
git push -u origin develop
```

**One-time setup (stale `origin/HEAD`):** After clone, align the remote’s symbolic ref so tools that follow `origin/HEAD` behave correctly:

```bash
git remote set-head origin -a
```

## GitHub default branch

GitHub’s default branch is `main`. **All pull requests must target `develop` explicitly** (for example `gh pr create --base develop`, or the web UI with base set to `develop`). Never rely on GitHub’s default when creating PRs, or the merge will bypass the integration layer.

## Branch Structure
```
main          ← production-ready only; never commit directly
  └─ develop  ← integration; all feature branches merge here first
       ├─ feature/m1-postgres-migration   ← milestone branches
       ├─ feature/m5-experiment-pages
       ├─ fix/issue-47-water-rock-ratio   ← issue branches
       ├─ fix/issue-52-icp-null-dilution
       └─ chore/add-experiment-id-index   ← inline/chore branches
```

## Branch Rules

### Milestone branches
- Named `feature/m<number>-<short-description>`
- Created from `develop` at milestone start
- One branch per milestone; sub-tasks are commits within it
- Integrated into `develop` via **pull request with base `develop`** (not direct merge to `main`) after agent review + Test Writer Agent pass

### Issue branches
- Named `fix/issue-<number>-<short-description>` (bug fixes)
- Named `feat/issue-<number>-<short-description>` (new feature issues)
- Created from `develop` before any code is written
- Merged to `develop` after task completes and tests pass
- Branch is deleted after merge

### Inline branches
- Required when the task changes any tracked file (code, migrations, config)
- Named by type:
  - `fix/<short-description>` — bug fix with no issue number
  - `feat/<short-description>` — small feature addition
  - `chore/<short-description>` — config, tooling, docs-only change
  - `refactor/<short-description>` — restructuring without behavior change
  - `infra/<short-description>` — server setup, deployment config, environment changes
- Skip branching only for: read-only tasks, documentation-only edits to
  `docs/working/`, or a change to a single comment or string literal
- Created from `develop` before any code is written
- Merged to `develop` after task completes

### Universal rules
- Never create a branch from `main`
- Never commit directly to `develop` or `main`
- Never force-push to `develop` or `main`
- Delete branches after successful merge
- If unsure whether a branch is needed, create one — it costs nothing

Routine commit, merge, and cleanup steps for agents: `.claude/commands/complete-task.md` (Steps 3–4).

## Commit messages

Subject-line prefixes and body bullets by task type: `.claude/CLAUDE.md` section 10.

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
