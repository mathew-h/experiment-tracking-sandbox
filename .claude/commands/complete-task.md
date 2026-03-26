# /complete-task

Use after finishing each sub-task or milestone phase.

## Step 1 — Quality pass
1. Run all relevant tests (`pytest` or `vitest`)
2. Run linters (`flake8`/`black` or `eslint`)
3. Confirm pre-merge checklist from `docs/GIT_WORKFLOW.md`

## Step 2 — Record the work (varies by task type)

### If task type = milestone
- Update `docs/working/plan.md`:
  - Mark the completed task
  - Log decisions made
  - Note what was tested
  - Record what comes next
- If a lasting architectural decision was made, also append to `docs/working/decisions.md`

### If task type = issue
- Append one entry to `docs/working/issue-log.md` (see format below)
- If the fix reveals something that affects milestone scope or ordering, note it in `docs/working/plan.md` under a "Discovered" section
- If a lasting architectural decision was made, append to `docs/working/decisions.md`

### If task type = inline
- Append one entry to `docs/working/issue-log.md` (see format below)
- Do NOT touch `plan.md` unless the change affected a locked component or milestone dependency
- If a lasting architectural decision was made, append to `docs/working/decisions.md`

## Issue-log entry format
```
## YYYY-MM-DD | <task type> <identifier or short description>
- **Files changed:** <list>
- **Tests added:** yes/no — <what kind>
- **Decision logged:** yes/no
```

## Step 3 — Commit
Commit all changes for this task first (required before push/merge). Use the format from `.claude/CLAUDE.md` section 10 (task-type-specific subject lines).

## Step 4 — Merge and clean up

### If task type = milestone
- Do not merge locally — milestone branches stay open until full milestone sign-off
- Push the branch: `git push origin <branch-name>`
- When opening a PR (for review or integration), use **`gh pr create --base develop`** (or the web UI with base `develop`). GitHub defaults to `main`; omitting an explicit base bypasses the integration layer.

### If task type = issue or inline (and a branch was created)
1. Run the pre-merge checklist from `docs/GIT_WORKFLOW.md`
2. Push the branch: `git push origin <branch-name>`
3. If tests pass and checklist is clear:
   - **Verify `develop` exists locally** before merging: `git rev-parse --verify develop` must succeed. If it fails, stop with a clear message: create `develop` per Prerequisites in `docs/GIT_WORKFLOW.md` — do not run `git checkout develop` and surface an opaque error.
   - Merge to develop: `git checkout develop && git merge --no-ff <branch-name>`
   - Delete the branch: `git branch -d <branch-name> && git push origin --delete <branch-name>`
4. If tests fail or checklist has blockers:
   - Do not merge
   - Report what is blocking and wait for user instruction

### If task type = inline and no branch was created
- You already committed on the current branch in Step 3 (must not be `develop` or `main`)
- If the current branch is `develop` or `main`, stop and ask the user

## Step 5 — Report
State what was completed, what was recorded, and where.
Wait for sign-off before starting the next task.
