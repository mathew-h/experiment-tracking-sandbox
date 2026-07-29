# ESLint baseline: repo violates its own zero-warnings rule

**Type:** chore
**Area:** `frontend/`
**Priority:** high (blocks enforcement of everything below it)

---

## Problem

`frontend/CLAUDE.md:36` states the standard as "ESLint + Prettier zero warnings", and
`frontend/package.json` encodes it:

```json
"lint": "eslint src --ext ts,tsx --report-unused-disable-directives --max-warnings 0"
```

The current tree reports 5 errors, so `npm run lint` exits non-zero. That means the rule
is aspirational rather than enforced: nobody can tell a pre-existing failure from one
they just introduced, so the signal is worthless and gets ignored.

## Fill in before starting

I could not run ESLint to capture the rule IDs — it exceeds the available command
timeout against this checkout. Paste the output of

```bash
cd frontend && npm run lint
```

into this section before work starts. The fix differs substantially depending on which
rules fire.

Config context (`frontend/.eslintrc.cjs`): extends `eslint:recommended`,
`plugin:@typescript-eslint/recommended`, `plugin:react-hooks/recommended`, with two
local overrides — `@typescript-eslint/no-unused-vars` as an error with `^_` ignore
patterns, and `no-console: error`. There is **no** `parserOptions.project`, so no
type-aware rules are active. That narrows the likely culprits to unused variables,
stray `console.*` calls, `react-hooks/exhaustive-deps`, or
`@typescript-eslint/no-explicit-any`.

## Proposal

1. Fix all 5. None of the rules above have expensive fixes, and a genuine
   false positive gets a line-scoped `// eslint-disable-next-line <rule> -- <why>`.
   `--report-unused-disable-directives` is already on, so a disable that stops being
   necessary becomes an error itself.
2. Do **not** relax the rules or add blanket `ignorePatterns` to reach green.
3. Once green, add `npm run lint` and `npm run type-check` to CI so the baseline cannot
   regress. Without this step the issue recurs.
4. Consider `react-hooks/exhaustive-deps` findings carefully. If any of the 5 are that
   rule, the missing dependency may be a real staleness bug rather than a lint nit, and
   should be split into its own issue rather than silenced.

## Acceptance criteria

- [ ] `cd frontend && npm run lint` exits 0
- [ ] `cd frontend && npm run type-check` exits 0
- [ ] Any `eslint-disable` added carries a `--` justification comment
- [ ] CI runs both commands on every PR to `develop`
- [ ] No rule severities were lowered and no new `ignorePatterns` entries were added

## Notes

Touching `frontend/package.json` invokes the deployment-critical rule in `CLAUDE.md` §5:
`package.json` and `package-lock.json` must be committed together and in sync, because
the lab PC's nightly `update.ps1` runs `npm ci`, which hard-fails if they disagree. If
this issue adds a dependency (e.g. a CI reporter), run `npm install` in `frontend/` and
commit both files in one commit.
