# Frontend Context

## Must Read Before Any Frontend Task
- `docs/DESIGN.md` — brand hex codes and UI vision
- `docs/CODE_STANDARDS.md` — TypeScript/React standards
- `.claude/skills/frontend-builder.md` — full role definition

## Key Rules (Non-Negotiable)
- Never hardcode hex values in components — always reference brand tokens from `frontend/src/assets/brand.ts`
- No inline styles — Tailwind utility classes only
- No `useEffect` + `useState` for data fetching — use React Query
- No `console.log` in committed code
- ESLint + Prettier zero warnings

## Chrome DevTools Loop
The conductor must explicitly enable this per task. It does not run autonomously.
Instructions are in `.claude/skills/frontend-builder.md`.

## Milestone 4 Prerequisite Check
Before starting any Milestone 4 work, verify `frontend/public/logo.png` exists
and `docs/DESIGN.md` has brand hex codes. If either is missing, stop and ask the user.
