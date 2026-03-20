# Frontend Context

## Must Read Before Any Frontend Task
- `docs/DESIGN.md` — brand hex codes and UI vision
- `docs/CODE_STANDARDS.md` — TypeScript/React standards
- `.claude/skills/frontend-builder.md` — full role definition

## Quick Commands

```bash
# Install dependencies
npm install

# Start dev server (Vite, default port 5173; may use 5174 if occupied)
npm run dev

# Build for production (output to frontend/dist/ — served by FastAPI)
npm run build

# Run tests
npx vitest

# Lint
npx eslint src --ext .ts,.tsx
```

**Vite port drift:** Each restart tries 5173, 5174, 5175… Check the startup log for the actual port.

**Important:** FastAPI serves `frontend/dist/` as static files. After `npm run build`, the backend serves the React app at `/`. All non-API routes return `index.html`.

## Key Rules (Non-Negotiable)
- Never hardcode hex values in components — always reference brand tokens from `frontend/src/assets/brand.ts`
- No inline styles — Tailwind utility classes only
- No `useEffect` + `useState` for data fetching — use React Query
- No `console.log` in committed code
- ESLint + Prettier zero warnings

## Firebase Setup (Required for Auth)
Copy `frontend/.env.example` to `frontend/.env.local` and fill in Firebase credentials.
Without this, the app starts but shows a "Firebase not configured" warning and auth is bypassed
(useful for UI-only dev work without Firebase credentials).

Test account: `labpc@addisenergy.com` (password matches email — dev only).

## Adding Fields to the Results Endpoint
Requires changes in exactly 3 places — missing any one silently omits the field from the UI:
1. `backend/api/schemas/results.py` — add to `ResultWithFlagsResponse`
2. `backend/api/routers/experiments.py` — populate in `get_experiment_results()`
3. `frontend/src/api/experiments.ts` — add to `ResultWithFlags` interface

## Design System
All color/font tokens in `frontend/src/assets/brand.ts` — never hardcode hex values in components.
Tailwind config mirrors these tokens. CSS custom properties in `frontend/src/styles/tokens.css`.
