# Skill: frontend-builder

## When Claude Loads This Skill
Load this file when the task involves: React components, Tailwind config,
brand tokens, the design system, Firebase auth integration, or any file
under `frontend/`.

## Role Definition
- Builds React components, pages, design system, and API client layer
- Applies the `frontend-design` skill — commits to a bold, precise aesthetic direction using user-provided brand tokens
- Uses the Chrome DevTools closed-loop for iterative UI verification
- Produces: React components, Tailwind config, brand token files, frontend tests
- **Requires before starting Milestone 4:** user-provided `logo.png` in `frontend/public/` and brand hex codes in `docs/DESIGN.md`

## Prerequisites Check
Before starting Milestone 4, verify:
- [ ] `frontend/public/logo.png` exists
- [ ] `docs/DESIGN.md` contains brand hex codes
If either is missing, stop and ask the user.

## Must Read Before Acting
- `docs/DESIGN.md` — brand hex codes and UI vision
- `docs/CODE_STANDARDS.md` — TypeScript/React standards
- The active milestone file from `docs/milestones/`

## Key Constraints
- React 18 + TypeScript strict mode; functional components only; props interfaces on every component
- React Query for all server state — no `useEffect` + `useState` for data fetching
- React Router v6 for navigation; Tailwind utility classes only — no inline styles
- Never hardcode hex values in components — always reference brand tokens from `frontend/src/assets/brand.ts`
- ESLint + Prettier zero warnings; no `console.log` in committed code

## Chrome DevTools Closed-Loop
The conductor must explicitly enable this per task. It does not run autonomously.

1. Agent writes or modifies a component
2. Agent opens `http://localhost:5173` in Chrome via Chrome DevTools MCP
3. Agent uses Chrome DevTools (console, network tab, elements inspector) to verify rendering, catch errors, and inspect API responses
4. Agent fixes any issues found and repeats until the component passes visual and functional checks
5. Agent reports to the conductor with a summary of what was verified

Available from Milestone 4 onward.

## Context7 Usage
Add `use context7` to any prompt involving: React, TanStack Query v5, React Router v6, Firebase SDK, Tailwind CSS v3, Vite.
