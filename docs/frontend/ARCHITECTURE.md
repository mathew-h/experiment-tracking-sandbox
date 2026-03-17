# Frontend Architecture

## Tech Stack

| Technology | Version | Role |
|------------|---------|------|
| React | 18 | UI framework |
| TypeScript | 5 (strict) | Type safety |
| Vite | 5 | Build tool and dev server |
| Tailwind CSS | 3 | Styling |
| TanStack Query | 5 | Server state / data fetching |
| Axios | 1 | HTTP client |
| Firebase Auth | 10 | Authentication |
| React Router | 6 | Client-side routing |

---

## Directory Structure

```
frontend/src/
├── assets/
│   └── brand.ts             # Single source of truth for all design tokens
├── auth/
│   ├── AuthContext.tsx       # Auth state, token refresh, signIn/signOut
│   ├── ProtectedRoute.tsx    # Route guard — redirects to /login if unauthenticated
│   └── firebaseConfig.ts     # Firebase SDK initialization + firebaseConfigured flag
├── api/
│   ├── client.ts             # Axios instance with error interceptor
│   ├── experiments.ts        # Experiment CRUD + notes
│   ├── samples.ts
│   ├── chemicals.ts
│   ├── analysis.ts
│   ├── dashboard.ts
│   ├── results.ts
│   └── bulkUploads.ts
├── components/ui/
│   ├── Button.tsx
│   ├── Input.tsx
│   ├── Select.tsx
│   ├── Card.tsx
│   ├── Badge.tsx
│   ├── Table.tsx
│   ├── Modal.tsx
│   ├── Toast.tsx
│   ├── Spinner.tsx
│   ├── FileUpload.tsx
│   └── index.ts             # Barrel export
├── layouts/
│   ├── AppLayout.tsx         # Sidebar + header, wraps all authenticated pages
│   └── AuthLayout.tsx        # Centered card, wraps Login
├── pages/
│   ├── Login.tsx
│   ├── Dashboard.tsx
│   ├── ExperimentList.tsx
│   ├── ExperimentDetail.tsx
│   ├── NewExperiment.tsx
│   ├── BulkUploads.tsx
│   ├── Samples.tsx
│   ├── Chemicals.tsx
│   └── Analysis.tsx
├── styles/
│   ├── tokens.css            # CSS custom properties (mirrors brand.ts)
│   └── index.css             # Tailwind imports + global utilities
├── App.tsx                   # Router and route definitions
└── main.tsx                  # React root + provider wrappers
```

---

## Provider Stack

Providers are layered in `main.tsx` from outermost to innermost:

```tsx
<QueryClientProvider client={queryClient}>   // TanStack Query
  <BrowserRouter>                            // React Router
    <AuthProvider>                           // Firebase auth state
      <ToastProvider>                        // Toast notifications
        <App />
      </ToastProvider>
    </AuthProvider>
  </BrowserRouter>
</QueryClientProvider>
```

`QueryClient` default options: `staleTime: 30_000ms`, `retry: 1`.

---

## Routing

Defined in `App.tsx`. Two layout contexts:

| Layout | Purpose | Auth required |
|--------|---------|---------------|
| `AuthLayout` | Login page — centered card with grid background | No |
| `AppLayout` | All app pages — fixed sidebar + header | Yes (via `ProtectedRoute`) |

**Route table:**

| Path | Page | Notes |
|------|------|-------|
| `/login` | `Login` | Public |
| `/` | `Dashboard` | Protected |
| `/experiments` | `ExperimentList` | Protected |
| `/experiments/new` | `NewExperiment` | Protected |
| `/experiments/:id` | `ExperimentDetail` | Protected |
| `/bulk-uploads` | `BulkUploads` | Protected |
| `/samples` | `Samples` | Protected |
| `/chemicals` | `Chemicals` | Protected |
| `/analysis` | `Analysis` | Protected |
| `*` | Redirect → `/` | |

`ProtectedRoute` shows `PageSpinner` while auth is loading, then redirects to `/login` if no user.

---

## Auth Flow

1. **App boot** — `AuthProvider` calls `onAuthStateChanged`. While resolving, `loading = true`.
2. **Unauthenticated** — `ProtectedRoute` redirects to `/login`.
3. **Login** — `signIn(email, password)` calls Firebase. On success, auth state updates automatically.
4. **Token lifecycle** — `AuthProvider` sets a 55-minute `setInterval` to call `user.getIdToken(true)` and refresh the token proactively before expiry.
5. **Axios interceptor** — `src/api/client.ts` attaches the current token to every request via an `Authorization: Bearer <token>` header. The header is updated whenever the token changes.
6. **Sign out** — `signOut()` clears Firebase session; `onAuthStateChanged` fires and clears `user`; router redirects to `/login`.

**Firebase bypass (dev mode):** If `.env.local` is missing or `VITE_FIREBASE_API_KEY` is empty, `firebaseConfigured = false`. `AuthProvider` skips `onAuthStateChanged`, `ProtectedRoute` passes through without redirecting, and the login page shows a warning. This lets the UI run without Firebase credentials.

---

## Data Fetching Pattern

All server state uses **TanStack Query**. Direct `useEffect` + `fetch` is not used.

**Queries:**
```tsx
const { data, isLoading, error } = useQuery({
  queryKey: ['experiments', { status }],
  queryFn: () => experimentsApi.list({ status }),
})
```

**Mutations:**
```tsx
const mutation = useMutation({
  mutationFn: experimentsApi.create,
  onSuccess: (data) => {
    queryClient.invalidateQueries({ queryKey: ['experiments'] })
    toast.success('Experiment created')
    navigate(`/experiments/${data.id}`)
  },
  onError: (err) => toast.error('Failed to create', err.message),
})
```

**Query key conventions:** Use the resource name as the first element, then filter/id params.

```
['experiments']                    // list
['experiments', id]                // single item
['experiments', { status }]        // filtered list
['reactor-status']                 // dashboard
```

---

## API Client

`src/api/client.ts` exports a single Axios instance:

```ts
export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30_000,
})
```

The response interceptor normalizes FastAPI errors: if the response body has `detail` as a string, it becomes `error.message`; if `detail` is an array of validation objects, the messages are joined and set as `error.message`. Callers never need to inspect the raw response shape.

Each resource has its own module in `src/api/` that exports:
- TypeScript interfaces for request and response shapes
- A const object (e.g. `experimentsApi`) with typed methods

---

## Dev Environment

**Dev server:** `npm run dev` — Vite on `http://localhost:5173` (host `0.0.0.0` for LAN access).

**API proxy:** All `/api/*` requests are forwarded to `http://localhost:8000` by Vite's proxy. No CORS configuration needed during development.

**Firebase:** Copy `.env.example` → `.env.local` and fill in values from the Firebase console. Without this file the app runs in bypass mode (no real auth).

**Path alias:** `@/*` resolves to `src/*`. Use `@/components/ui` not `../../components/ui`.

**Production build:** `npm run build` — outputs to `frontend/dist/`. FastAPI serves `dist/` as static files at `/`.
