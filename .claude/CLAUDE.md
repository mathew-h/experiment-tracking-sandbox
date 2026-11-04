# CLAUDE.md — Lab Experiment Tracking System
> Do not modify this file unless explicitly directed by the user.

---

## 1. Start Every Session With This

1. Run `/start-task` — classify task mode (`milestone` / `issue` / `inline`), create or confirm the branch, load context, confirm scope. The mode governs which context files load and must be stated in the scope confirmation.
2. Never begin coding without completing the `/start-task` checklist
3. **Git:** follow `docs/GIT_WORKFLOW.md`. Branch in `/start-task` Step 2 before context load; state branch (or skip) in Step 4 scope confirmation
4. **Pull requests:** Always use `--base develop` when creating PRs (e.g. `gh pr create --base develop`). Never rely on GitHub’s default branch.

---

## 2. Project Overview

A laboratory experiment tracking system for a small geochemistry team (8 users).
Researchers log experiments, upload bulk analytical data, track samples and chemicals,
and visualize reactor status.

**Current state:** React 18 + FastAPI + PostgreSQL (see `docs/STACK.md` for full table)

**Deployment:** Single always-on lab PC, LAN only, no cloud, no Docker in production.

---

## 3. Role Skills

Role skills live in `.claude/skills/<name>/SKILL.md` and load on demand from their descriptions:
- `conductor` — multi-step work: decomposing a goal, sub-agent handoffs, review routing
- `db-architect` — schema, migrations, calculation registry
- `api-developer` — FastAPI, Pydantic, calculation formulas
- `frontend-builder` — React, Tailwind, design system
- `test-writer` — pytest, vitest, coverage

---

## 4. What Is Locked

Full details in `docs/LOCKED_COMPONENTS.md`. Summary:

- `database/models/` — field names, types, relationships: do not change without explicit instruction
- `backend/services/bulk_uploads/` — parser logic: do not modify without explicit instruction
- `alembic/versions/` — never delete or squash migration files
- Firebase auth — do not modify without explicit instruction
- All enums in `enums.py` — changing these breaks existing data

### Frontend dependency rule (deployment-critical)

`frontend/package.json` and `frontend/package-lock.json` **must always be committed together in the same commit** and must always be in sync.

The lab PC's `update.ps1` runs `npm ci` (not `npm install`) on every nightly update. `npm ci` refuses to mutate either file and hard-fails if they disagree — this breaks the entire deploy pipeline until manually resolved on the lab PC.

**To add or bump a frontend dependency:**
```bash
cd frontend
npm install <package>        # or edit package.json then run npm install
# verify both package.json AND package-lock.json changed
git add package.json package-lock.json
git commit -m "chore: ..."   # both files in the same commit
```

**Never:**
- Edit version strings in `package.json` directly without running `npm install` in `frontend/` immediately after
- Move deps between `dependencies` and `devDependencies` without running `npm install` after
- Commit `package.json` without `package-lock.json` (or vice versa)

### Tests share one database

Never run two `pytest` processes at the same time: every run uses the shared `experiments_test` database, and parallel runs (or an interrupted one) corrupt each other's schema and data.

---

## 5. Key Reference Files

| Need | Read |
|------|------|
| Schema details | `.claude/rules/MODELS.md` (index → topic files) |
| Derived field formulas | `docs/CALCULATIONS.md` |
| Milestone details | `docs/milestones/[milestone file]` |
| Locked components | `docs/LOCKED_COMPONENTS.md` |
| Code standards | `docs/CODE_STANDARDS.md` |
| Git workflow | `docs/GIT_WORKFLOW.md` |
| Environment variables | `docs/ENVIRONMENT.md` |
| Read-only psql/reporting access | `docs/PSQL_ACCESS.md` |
| Design system | `docs/DESIGN.md` |
| Agent system full reference | `docs/AGENT_SYSTEM.md` |
| Directory structure | `docs/DIRECTORY_STRUCTURE.md` |

---

## 6. Stop and Ask the User When

- A schema change affects more than one model
- A new third-party package is needed
- Any bulk upload parser needs modification
- A migration cannot be written as purely additive
- A decision would affect the production database or the lab PC service
- Firebase authentication configuration needs to change
- A derived field formula is ambiguous or undocumented
- A browser (Chrome DevTools) check reveals a bug that needs a schema or API change to fix
- Any test is failing and the fix is not obvious within 2 attempts
- Estimated scope expands significantly beyond what was agreed

When escalating: state the ambiguity, the options, your recommendation. Then wait.

---

## 7. Commit Format

**Milestone tasks:**
```
[M<number>] <imperative description>

- Detail if needed
- Tests added: yes/no
- Docs updated: yes/no
```

**Issue tasks:**
```
[#<issue-number>] <imperative description>

- Detail if needed
- Tests added: yes/no
- Docs updated: yes/no
```

**Inline tasks:**
```
[fix|feat|chore|refactor] <imperative description>

- Detail if needed
- Tests added: yes/no
- Docs updated: yes/no
```

All descriptions: imperative mood, under 50 characters, no trailing period.

---

## 8. MCP Servers
claude.ai connectors (Slack, Microsoft 365, Notion, Claude Docs, ...) are not needed here and cost context. They come from each developer's claude.ai account, so `.mcp.json` cannot disable them (it has no `disabledMcpServers` key). Disable them per developer with `/mcp disable "claude.ai <Name>"` in this project; it persists to `~/.claude.json`.

---

## 9. Documentation Sync — `docs/project_context/`

`docs/project_context/` is the **external team folder**. It receives copies of all documentation
files so the broader team can stay informed of schema changes, API updates, and app functionality.

### Automatic sync (hook)
A `PostToolUse` hook in `.claude/settings.json` runs `.claude/hooks/sync_docs_to_project_context.py`
after every `Write` or `Edit` tool call. It copies any file written inside `docs/` (excluding
`docs/working/` and `docs/project_context/` itself) to `docs/project_context/`.

**Do not write directly to `docs/project_context/`** — the hook handles synchronization automatically.
Edits made through Bash or Python scripts bypass the hook; run the sync script with `--all` afterwards.

Documentation updates required before committing are listed in `/complete-task` Step 1.
