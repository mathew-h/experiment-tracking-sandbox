# /start-task

Use at the beginning of every work session. Classify the task type, create or confirm the working branch, then load only the context that type requires.

---

## Step 1 — Classify the task (do this before reading any files)

Determine which task type applies based on what the user provided:

| Task type   | Signal                                                                 |
| ----------- | ---------------------------------------------------------------------- |
| **milestone** | User references a milestone ("work on M5", "continue bulk uploads") |
| **issue**     | User provides a GitHub issue number or URL                            |
| **inline**    | User describes the task directly in the prompt (no issue, no milestone reference) |

---

## Step 2 — Create or confirm the working branch

Do this **before** reading any context files or writing any code. Full policy: `docs/GIT_WORKFLOW.md`.

### If task type = milestone
- Confirm the milestone branch exists and check it out:
  `git checkout feature/m<number>-<description>`
- If it doesn't exist: `git checkout -b feature/m<number>-<description> develop`

### If task type = issue
- Read labels only (before Step 3): e.g. `gh issue view <number> --json labels,title` — full issue context comes in Step 3
- Determine branch type from the issue labels:
  - Label `bug` → `fix/issue-<number>-<short-description>`
  - Label `enhancement` or `feature` → `feat/issue-<number>-<short-description>`
  - Label `chore`, `docs`, `refactor` → use matching prefix (`chore/issue-…`, etc.) per `docs/GIT_WORKFLOW.md`
- Create and check out: `git checkout -b <branch-name> develop`
- Confirm with user: "Created branch `fix/issue-47-water-rock-ratio`. Proceeding." (use the actual branch name)

### If task type = inline
- Decide if a branch is needed:
  - **Skip branching if:** task is read-only, or only touches `docs/working/`, or is
    a single-line comment/string fix
  - **Create a branch for everything else**
- Choose the prefix from: `fix/`, `feat/`, `chore/`, `refactor/`
- Name it from the task description: `git checkout -b fix/icp-null-dilution develop`
- State the branch name to the user before proceeding (or state that branching was skipped and why)

### All task types
- Run `git status` to confirm you are on the correct branch
- If the working tree is dirty, stop and ask the user how to handle it before proceeding

---

## Step 3 — Load context for that task type

### If task type = issue or inline

- Read last 5 entries of `docs/working/issue-log.md` — check for recent changes to the same files or domain

### If task type = milestone

1. Read `docs/working/plan.md` — orient to current status (full read).
2. Read `docs/milestones/MILESTONE_INDEX.md` — confirm active milestone.
3. Read the active milestone file from `docs/milestones/`.
4. Run `git log --oneline -10`.
5. Identify which sub-agent skill(s) are needed and read them from `.claude/skills/` (see `.claude/CLAUDE.md` section 4).
6. Update `docs/working/plan.md` with the task being started.

### If task type = issue

1. Read `docs/working/plan.md` — **quick orientation only**: through `## Current State` (the bullet list) and the following `---`; do not read the milestone detail section below that.
2. Fetch the issue via `gh issue view <number>` — read labels, description, acceptance criteria.
3. Run `git log --oneline -5`.
4. Read only the sub-agent skill file(s) in `.claude/skills/` relevant to the issue labels:
   - Label `backend` or `api` → `api-developer.md`
   - Label `frontend` or `ui` → `frontend-builder.md`
   - Label `db` or `schema` → `db-architect.md`
5. Do **not** update `plan.md` until the task completes.

### If task type = inline

1. Read `docs/LOCKED_COMPONENTS.md` — confirm nothing in scope is locked.
2. Read `docs/CODE_STANDARDS.md` — confirm the applicable language section.
3. Identify the minimum set of files that need to change.
4. Do **not** read `plan.md` or any milestone file unless the task turns out to touch milestone work.

---

## Step 4 — Scope confirmation (all task types)

Before writing any code, state:

- What you are going to do
- **Git:** current branch (or that branching was skipped per Step 2); new vs existing
- Which files will be created or modified
- What the acceptance criteria are
- Estimated complexity (single file / multi-file / cross-layer)

Wait for user confirmation before proceeding.

---

## Step 5 — Escalate back to milestone mode if needed

If an inline or issue task reveals it requires a schema change, new package, or modification to a locked component — stop, re-run from Step 2 (branch) and Step 3 (milestone path), and surface the escalation per `.claude/CLAUDE.md` section 9 before continuing.
