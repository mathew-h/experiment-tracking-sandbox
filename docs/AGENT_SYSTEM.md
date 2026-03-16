# Agent System — Roles and Responsibilities

The **Conductor Agent** coordinates all sub-agents. It does not implement features itself — it decomposes, delegates, verifies, and reports.

## Sub-Agent Definitions

### db-architect
- Handles all database schema changes, Alembic migrations, PostgreSQL queries
- Owns the calculation engine trigger registry (`backend/services/calculations/registry.py`)
- Produces: migration files, updated `docs/SCHEMA.md`, model integrity tests
- Triggered: any time a schema change, migration, or calculation trigger rule is needed
- Must read `docs/SCHEMA.md` and `MODELS.md` before any action

### api-developer
- Builds FastAPI routers, Pydantic schemas, calculation engine formula modules, bulk upload service wrappers
- Produces: router files, schema files, calculation formula modules, endpoint tests
- Triggered: any time a new endpoint, schema, or service function is needed
- Coverage target: 80% minimum on all new backend code

### frontend-builder
- Builds React components, pages, design system, and API client layer
- Applies the `frontend-design` skill — commits to a bold, precise aesthetic direction using user-provided brand tokens
- Uses the Chrome DevTools closed-loop for iterative UI verification
- Produces: React components, Tailwind config, brand token files, frontend tests
- **Requires before starting Milestone 4:** user-provided `logo.png` in `frontend/public/` and brand hex codes in `docs/DESIGN.md`

### Test Writer Agent
- Generates automated tests for every new feature and code change
- Produces: test plan document + implemented test files
- Triggered: after every feature branch is complete, before any merge
- Coverage target: 80% minimum on all new code
- Tools: pytest + pytest-asyncio (backend), Vitest + React Testing Library (frontend)

### Documentation Agent
- Ensures every function, endpoint, component, and feature is documented
- Produces: developer docs (docstrings, inline comments, architecture notes) and user-facing docs
- Triggered: at every milestone completion and whenever a public API or UI changes
- Must maintain `docs/sample_data/FIELD_MAPPING.md`
- Must maintain `docs/CALCULATIONS.md` — kept in sync with the implementation in `backend/services/calculations/`

## Conductor Workflow (mandatory for every task)

```
1.  Receive high-level goal from user
2.  Invoke Superpowers `brainstorming` skill — refine requirements, explore alternatives,
    surface trade-offs. Do not proceed until the design is user-approved.
3.  Invoke Superpowers `writing-plans` skill — produce bite-sized tasks (2-5 min each)
    with exact file paths, complete code, and verification steps.
4.  Identify which milestone the task belongs to (see docs/milestones/MILESTONE_INDEX.md)
5.  Verify the milestone's prerequisites are complete
6.  Assign sub-tasks to appropriate agents
7.  Sub-agents: add "use context7" to any prompt requiring current library docs
    (FastAPI, SQLAlchemy, Alembic, React, TanStack Query, Firebase, Tailwind, Vite)
8.  Invoke Superpowers `subagent-driven-development` — dispatch one subagent per task
    with two-stage review (spec compliance, then code quality)
9.  Route completed code through Code Review plugin before Test Writer Agent sees it
10. Route completed features to Test Writer Agent for test coverage
11. Route completed milestones to Documentation Agent for docs update
12. Documentation Agent runs `/revise-claude-md` to capture session learnings
13. Summarize milestone progress to user
14. Wait for user sign-off before advancing to next milestone
```

Never skip steps 9, 10, or 11. Never self-merge without review.

## Chrome DevTools Closed-Loop (frontend-builder only)

Once the React dev server is running, the `frontend-builder` subagent may use the Chrome DevTools MCP plugin to iterate on UI without requiring manual oversight per change. The loop:

1. Agent writes or modifies a component.
2. Agent opens `http://localhost:5173` in Chrome via Chrome DevTools MCP.
3. Agent uses Chrome DevTools (console, network tab, elements inspector) to verify rendering, catch errors, and inspect API responses.
4. Agent fixes any issues found and repeats until the component passes visual and functional checks.
5. Agent reports to the conductor with a summary of what was verified.

The conductor enables this loop explicitly per task. It does not run autonomously without a scoped instruction. Available from Milestone 4 onward.

## Plugins and MCP Capabilities

The following plugins are active for this project. They are **mandatory workflow components**, not optional enhancements.

**Install command (Cursor Agent chat):** `/add-plugin <plugin-name>`

### Superpowers
**Plugin:** `superpowers` | [claude.com/plugins/superpowers](https://claude.com/plugins/superpowers)

| Skill | When to invoke |
|---|---|
| `brainstorming` | Before starting any milestone — refine requirements, explore alternatives |
| `writing-plans` | After brainstorming — produce bite-sized task list with file paths and verification steps |
| `subagent-driven-development` | During implementation — one fresh subagent per task, two-stage review |
| `test-driven-development` | All implementation tasks — RED-GREEN-REFACTOR cycle, write test before code |
| `requesting-code-review` | Between tasks — check spec compliance and code quality before Test Writer Agent |
| `systematic-debugging` | Any time a bug requires root-cause analysis |
| `finishing-a-development-branch` | When milestone tasks are complete — verify tests, present merge/PR options |

### Context7
**Plugin:** `context7` (MCP) | [claude.com/plugins/context7](https://claude.com/plugins/context7)

Provides live, version-specific documentation. Add `use context7` to any prompt involving a library-specific pattern.

| Library | When to use |
|---|---|
| FastAPI | Before implementing any endpoint, dependency injection, middleware |
| SQLAlchemy 2.x | Before writing queries (`select()`, `Session.execute()`), relationships, async patterns |
| Alembic | Before writing any migration (`upgrade`/`downgrade` functions, batch ops) |
| Pydantic v2 | Before writing schemas, validators, `model_validate` patterns |
| TanStack Query v5 | Before implementing React Query hooks, mutations, cache invalidation |
| React Router v6 | Before implementing routing, protected routes, loaders |
| Firebase Admin SDK | Before writing token verification or auth patterns |
| Tailwind CSS v3 | Before configuring `tailwind.config.ts` or using new utility classes |
| Vite | Before configuring proxy, build output, or env vars |
| structlog | Before configuring processors, context variables, or log output format |

### CLAUDE.md Management
**Plugin:** `claude-md-management` | [claude.com/plugins/claude-md-management](https://claude.com/plugins/claude-md-management)

| Command | When |
|---|---|
| `audit my CLAUDE.md files` | Start of a new milestone |
| `/revise-claude-md` | End of every session |

### Frontend Design
**Plugin:** `frontend-design` | [claude.com/plugins/frontend-design](https://claude.com/plugins/frontend-design)
**Agent:** `frontend-builder` only | Available from Milestone 4 onward

### GitHub
**Plugin:** `github` (MCP) | [claude.com/plugins/github](https://claude.com/plugins/github)

| Use case | Command pattern |
|---|---|
| Create PR from feature branch to `develop` | After `Superpowers finishing-a-development-branch` signs off |
| Review open PRs | Before merging `develop` → `main` |
| Check CI/CD status | After pushing a feature branch |
| Create issues for escalation items | When stopping for user sign-off per escalation rules |

### Code Review
**Plugin:** `code-review` | [claude.com/plugins/code-review](https://claude.com/plugins/code-review)

Step 9 of the Conductor Workflow — runs before Test Writer Agent on every feature.
- Confidence-based filtering: only surface issues above medium confidence
- Critical issues block progress; informational issues are logged

### Playwright
**Plugin:** `playwright` (MCP) | [claude.com/plugins/playwright](https://claude.com/plugins/playwright)

| Test type | Milestone |
|---|---|
| Component smoke tests (login, protected routes) | Milestone 4 |
| Experiment creation round-trip | Milestone 5 |
| Bulk upload file drag-and-drop flow | Milestone 6 |
| Dashboard auto-refresh and filter combinations | Milestone 7 |
| All 6 E2E user journeys | Milestone 8 |

### Security Guidance
**Plugin:** `security-guidance` | [claude.com/plugins/security-guidance](https://claude.com/plugins/security-guidance)
**Anthropic Verified**

Fires as a hook — no explicit invocation needed. Watch for warnings about:
- Raw SQL string construction (use SQLAlchemy parameterized queries only)
- Firebase token handling (never log tokens)
- CORS misconfiguration
- File path traversal in bulk upload endpoints

### Pyright LSP
**Plugin:** `pyright-lsp` | [claude.com/plugins/pyright-lsp](https://claude.com/plugins/pyright-lsp)
**Anthropic Verified**

Zero Pyright errors is a pre-merge requirement. Enforces the "no `Any` without justification" rule.

### TypeScript LSP
**Plugin:** `typescript-lsp` | [claude.com/plugins/typescript-lsp](https://claude.com/plugins/typescript-lsp)
**Anthropic Verified**

Strict mode — zero TypeScript errors is a pre-merge requirement. Available from Milestone 4 onward.

### Recommended Additional Plugins

| Plugin | Install command | Value |
|---|---|---|
| `firebase` | `/add-plugin firebase` | Manage Firebase auth project, inspect users |
| `code-simplifier` | `/add-plugin code-simplifier` | Simplify recently modified code after refactoring milestones |
| `pr-review-toolkit` | `/add-plugin pr-review-toolkit` | Specialized agents for comments, types, quality on PRs |
| `postman` | `/add-plugin postman` | API lifecycle management — sync from FastAPI OpenAPI spec |
| `semgrep` | `/add-plugin semgrep` | Static analysis for security vulnerabilities |

## Sample Data File

Located at: `docs/sample_data/representative_sample.xlsx`

This file is the ground truth for what data fields the application must support. Before implementing any data model change, upload feature, or dashboard visualization, verify it accounts for all columns in this file.

If this file does not yet exist, stop and ask the user to provide it before proceeding with any data-layer work.

The Documentation Agent maintains `docs/sample_data/FIELD_MAPPING.md` which maps every column to its corresponding database model and field.
