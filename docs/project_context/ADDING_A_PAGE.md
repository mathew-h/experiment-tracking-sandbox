# Adding a Page

Follow these steps to add a new page to the frontend. Steps 1–3 are always required. Steps 4–5 are needed when the page fetches or mutates data.

---

## Step 1 — Create the page component

Create `src/pages/MyPage.tsx`:

```tsx
export default function MyPage() {
  return (
    <div>
      <h1 className="text-xl font-semibold text-ink-primary">My Page</h1>
    </div>
  )
}
```

Rules:
- Default export only — no named export for pages.
- Keep the component focused on layout and data fetching. Move complex sub-sections into local components in the same file or a `src/pages/my-page/` subfolder.
- No `console.log` — ESLint enforces `no-console: error`.
- All hooks (`useState`, `useQuery`, `useNavigate`, etc.) must appear before any conditional `return`.

---

## Step 2 — Register the route

Open `src/App.tsx` and add the route inside the `<Route element={<AppLayout />}>` block:

```tsx
import MyPage from '@/pages/MyPage'

// Inside the protected AppLayout block:
<Route path="/my-page" element={<MyPage />} />
```

If the page should be public (no auth required), add it outside the `ProtectedRoute` block alongside `/login`.

---

## Step 3 — Add the nav item (if user-navigable)

Open `src/layouts/AppLayout.tsx` and add an entry to the `navItems` array:

```tsx
const navItems = [
  { label: 'Dashboard', path: '/', icon: <GridIcon /> },
  // ...existing items...
  { label: 'My Page', path: '/my-page', icon: <MyIcon /> },
]
```

Icons come from `lucide-react`. Pick one from the existing imports or add a new import at the top of the file.

---

## Step 4 — Add an API module (if the page talks to the backend)

Create `src/api/myResource.ts`:

```ts
import { apiClient } from '@/api/client'

// 1. Define response/request types
export interface MyResource {
  id: number
  name: string
  created_at: string
}

export interface CreateMyResourcePayload {
  name: string
}

// 2. Export a single API object with typed methods
export const myResourceApi = {
  list: (): Promise<MyResource[]> =>
    apiClient.get<MyResource[]>('/my-resource').then((r) => r.data),

  get: (id: number): Promise<MyResource> =>
    apiClient.get<MyResource>(`/my-resource/${id}`).then((r) => r.data),

  create: (payload: CreateMyResourcePayload): Promise<MyResource> =>
    apiClient.post<MyResource>('/my-resource', payload).then((r) => r.data),

  patch: (id: number, payload: Partial<CreateMyResourcePayload>): Promise<MyResource> =>
    apiClient.patch<MyResource>(`/my-resource/${id}`, payload).then((r) => r.data),

  delete: (id: number): Promise<void> =>
    apiClient.delete(`/my-resource/${id}`).then(() => undefined),
}
```

Rules:
- Always type the Axios generic (`apiClient.get<T>`).
- Chain `.then((r) => r.data)` — return the data directly, not the Axios response.
- Interfaces go at the top of the file, the API object at the bottom.

---

## Step 5 — Fetch data in the page

Use TanStack Query. Do not use `useEffect` + `fetch`.

**Reading data:**

```tsx
import { useQuery } from '@tanstack/react-query'
import { myResourceApi } from '@/api/myResource'
import { Spinner, PageSpinner } from '@/components/ui'

export default function MyPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['my-resource'],
    queryFn: myResourceApi.list,
  })

  if (isLoading) return <PageSpinner />
  if (error) return <p className="text-status-error">{error.message}</p>

  return (
    <ul>
      {data?.map((item) => (
        <li key={item.id}>{item.name}</li>
      ))}
    </ul>
  )
}
```

**Writing data (mutation):**

```tsx
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/components/ui'

export default function MyPage() {
  const queryClient = useQueryClient()
  const toast = useToast()

  const create = useMutation({
    mutationFn: myResourceApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-resource'] })
      toast.success('Created successfully')
    },
    onError: (err: Error) => toast.error('Failed to create', err.message),
  })

  return (
    <Button
      loading={create.isPending}
      onClick={() => create.mutate({ name: 'New item' })}
    >
      Create
    </Button>
  )
}
```

**Query key conventions:**
```
['my-resource']              // full list
['my-resource', id]          // single item
['my-resource', { filter }]  // filtered list
```

Invalidate the list key after any create/update/delete so the UI stays in sync.

---

## Checklist

- [ ] `src/pages/MyPage.tsx` created with default export
- [ ] Route added in `src/App.tsx`
- [ ] Nav item added in `src/layouts/AppLayout.tsx` (if user-navigable)
- [ ] API module in `src/api/` (if page calls the backend)
- [ ] Data fetched via `useQuery` / mutated via `useMutation`
- [ ] `npm run type-check` — zero errors
- [ ] `npm run lint` — zero warnings
