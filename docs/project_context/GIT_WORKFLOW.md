# Git Workflow

## Mental model: integration vs production

`main` has two jobs in many small teams: **integration** (where work lands) and **production** (what the deploy reads). If those are the same branch, multiple agents or terminals all branch from and merge back to `main`, you get a traffic jam—concurrent edits on one line of history, merge conflicts, and half-finished features shipping on the next deploy.

**Correct split:**

- **`main`** — production only. The deploy reads this. Do not commit here directly. The only routine change to `main` is promoting tested work from `develop` when *you* decide it is ready (see [Deploy and `main`](#deploy-and-main)).
- **`develop`** — integration. **All** feature work lands here first (via branches and PRs or local merges). Multiple terminals stay isolated by using different topic branches; `develop` only receives completed, tested work.

```
main       ← production only; deploy reads this; never touch directly for day-to-day work
  └─ develop  ← where ALL integration work lands first
       ├─ feat/thing-a    ← e.g. terminal / task 1
       ├─ fix/thing-b     ← e.g. terminal / task 2
       └─ chore/thing-c   ← e.g. terminal / task 3
```

## Core rules

| Rule | Why |
|------|-----|
| Every terminal branches from **`develop`**, not **`main`** | Isolated lines of work; no stomping on production history |
| Every terminal lands work on **`develop`**, not **`main`** | Keeps **`main`** stable until you promote |
| Only **you** (or a **scheduled, explicit** job) merges **`develop` → `main`** | You control exactly what deploys |
| Never commit directly to **`develop`** or **`main`** | Always use a topic branch |

## Deploy and `main`

The deploy trigger should **not** be “whatever merged to `main` from random terminals.” It should be: **`develop` is stable → then promote to `main`** (on your schedule).

Pick one approach:

1. **Deploy from `develop`** — Point the deploy job at `develop` (simplest if you can rename the target). Promotion is implicit: what you merge to `develop` is what runs.
2. **Deploy from `main`** — Keep the job on `main`, but **only** advance `main` when you intend to release, e.g. after a stable stretch on `develop`:

   ```bash
   git checkout main
   git pull
   git merge develop
   git push
   ```

   A scheduled “pull latest `main`” at 2am then picks up **accumulated, intentional** releases—not accidental concurrent merges.

Touching **`main` for a normal feature/fix flow is wrong**; **`git merge develop` on `main` (or equivalent release step) is the right time** to touch `main`.

## Multiple terminals (or agents)

Each session should use its **own topic branch** off **`develop`**, merge back to **`develop`**, then delete the branch. Branches do not conflict with each other; conflicts are resolved when merging into `develop`.

1. `git checkout develop && git pull` — start from current integration tip  
2. `git checkout -b fix/my-isolated-task develop` — branch from **`develop`** (adjust prefix: `feat/`, `chore/`, etc.; see [Branch rules](#branch-rules))  
3. Do work; commit on the topic branch  
4. Land on **`develop`**: merge locally (`git checkout develop && git merge fix/my-isolated-task`) **or** open a PR with base **`develop`** (required for some flows; see milestone/issue rules below)  
5. `git branch -d fix/my-isolated-task` (after merge)

**Stale IDE/git context:** A snapshot of branch or status taken at session open may not match another terminal’s live state. If `develop` is dirty or mid-merge, fix that before branching; for heavy parallel work, optional **git worktrees** (separate directories per branch) avoid one working tree blocking another—see `.gitignore` (`.worktrees/`) and `git worktree add`.

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

## Branch structure

```
main          ← production-ready only; never commit directly
  └─ develop  ← integration; all feature branches merge here first
       ├─ feature/m1-postgres-migration   ← milestone branches
       ├─ feature/m5-experiment-pages
       ├─ fix/issue-47-water-rock-ratio   ← issue branches
       ├─ fix/issue-52-icp-null-dilution
       └─ chore/add-experiment-id-index   ← inline/chore branches
```

## Branch rules

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
