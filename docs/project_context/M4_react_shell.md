# Milestone 4: React Frontend — Shell and Authentication

**Owner:** frontend-builder (primary), Documentation Agent
**Branch:** `feature/m4-react-shell`

**Prerequisite:** User must provide `frontend/public/logo.png` and brand hex codes in `docs/DESIGN.md` before this milestone begins. Stop and ask if either is missing.

**Tasks:**

**4a.** Scaffold Vite + React + TypeScript strict mode. Install Tailwind CSS, React Router v6, TanStack Query v5, Axios, Firebase SDK. Configure ESLint + Prettier. Configure Vite proxy for `/api/*` → `http://localhost:8000`.

**4b. Design system** (apply `frontend-design` skill)
- Commit to a bold, precise aesthetic direction appropriate for a scientific instrument dashboard
- Use user-provided hex codes from `docs/DESIGN.md` as the palette foundation
- `frontend/src/assets/brand.ts` — all brand color tokens, font tokens, spacing scale (single source of truth)
- Wire into `tailwind.config.ts` and `frontend/src/styles/tokens.css`
- `frontend/src/components/ui/` — `Button`, `Input`, `Select`, `Table`, `Card`, `Badge`, `Modal`, `Toast`, `Spinner`, `FileUpload`
- Never hardcode hex values in components — always reference brand tokens

**4c.** App shell: `AppLayout.tsx` (sidebar + header with logo), `AuthLayout.tsx`, navigation items: Dashboard, Experiments, New Experiment, Bulk Uploads, Samples, Chemicals, Analysis.

**4d.** Firebase auth: `FirebaseProvider.tsx`, `ProtectedRoute.tsx`, `Login.tsx`. Token storage, Axios interceptor, silent refresh on expiry.

**4e.** API client: `src/api/client.ts` (Axios + auth header interceptor), one domain file per backend router. All API calls via React Query.

**4f.** Page stubs for all routes.

**Acceptance criteria:** Firebase login works; protected routes redirect correctly; ESLint zero warnings; brand tokens match user-provided assets; logo renders; Chrome DevTools loop confirms no console errors.

**Documentation Agent:** `docs/frontend/ARCHITECTURE.md`, `docs/frontend/ADDING_A_PAGE.md`, `docs/frontend/DESIGN_SYSTEM.md`.
