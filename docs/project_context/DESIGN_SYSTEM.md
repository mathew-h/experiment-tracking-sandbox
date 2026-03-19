# Design System

## Philosophy

The UI aims for a **precision-instrument aesthetic**: dark navy surfaces, a sharp red accent, monospaced data values, and minimal chrome. The goal is a dashboard that looks like it belongs in a lab — not a consumer app.

Two fonts:
- **Inter** — UI labels, navigation, body text
- **JetBrains Mono** — numeric data values, IDs, measurement outputs

---

## Design Tokens

`src/assets/brand.ts` is the single source of truth. `src/styles/tokens.css` mirrors these as CSS custom properties. `tailwind.config.ts` extends Tailwind with the same values.

**Never hardcode hex values in components.** Always reference Tailwind utility classes or CSS variables.

### Color Palette

#### Navy (surfaces)

| Token | Value | Tailwind class | Use |
|-------|-------|----------------|-----|
| `navy.base` | `#05172B` | `bg-navy-base` | Page background |
| `navy.raised` | `#0a2440` | `bg-navy-raised` | Cards, panels |
| `navy.overlay` | `#0e3158` | `bg-navy-overlay` | Modals, dropdowns |
| `navy.border` | `#1a3a5c` | `border-navy-border` | Dividers, borders |
| `navy.muted` | `#133355` | `bg-navy-muted` | Subtle backgrounds |

#### Accent Red

| Token | Value | Tailwind class | Use |
|-------|-------|----------------|-----|
| `red.primary` | `#FD4437` | `text-red-primary`, `bg-red-primary` | Primary actions, active state |
| `red.dark` | `#d93020` | `bg-red-dark` | Hover state on red |
| `red.light` | `#ff6b5e` | `text-red-light` | Subtle red text |

#### Ink (text)

| Token | Value | Tailwind class | Use |
|-------|-------|----------------|-----|
| `ink.primary` | `#F0F4F8` | `text-ink-primary` | Primary text |
| `ink.secondary` | `#8BACC8` | `text-ink-secondary` | Labels, captions |
| `ink.muted` | `#4d6e8a` | `text-ink-muted` | Placeholder, disabled |

#### Status Colors

| Token | Tailwind class | Use |
|-------|----------------|-----|
| success | `text-status-success` / `bg-status-success` | ONGOING, success states |
| info | `text-status-info` / `bg-status-info` | COMPLETED |
| warning | `text-status-warning` | Warnings |
| error | `text-status-error` | Errors, CANCELLED |
| neutral | `text-status-neutral` | Inactive |

### Typography

```
font-sans      → Inter (UI text)
font-mono      → JetBrains Mono (code, IDs)
font-mono-data → JetBrains Mono with tabular-nums (numeric values)
```

`font-mono-data` is a global utility class in `styles/index.css`. Use it on all measurement outputs, yields, concentrations, and IDs.

### Spacing

| Token | Value | Tailwind |
|-------|-------|---------|
| Sidebar width | `240px` | `w-[240px]` |
| Header height | `56px` | `h-[56px]` |
| Card padding | `20px` | `p-5` |
| Section gap | `24px` | `gap-6` |

---

## Component Library

All components live in `src/components/ui/` and are exported from `src/components/ui/index.ts`.

```ts
import { Button, Input, Card, Badge, Table, Modal, Toast, Spinner, FileUpload } from '@/components/ui'
```

---

### Button

```tsx
<Button variant="primary" size="md" loading={false}>
  Save
</Button>
```

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `variant` | `'primary' \| 'secondary' \| 'ghost' \| 'danger' \| 'outline'` | `'secondary'` | Visual style |
| `size` | `'xs' \| 'sm' \| 'md' \| 'lg'` | `'md'` | |
| `loading` | `boolean` | `false` | Shows spinner, disables interaction |
| `leftIcon` | `ReactNode` | — | Icon before label |
| `rightIcon` | `ReactNode` | — | Icon after label |

Extends all `<button>` HTML attributes.

**Variants:**
- `primary` — red background, white text. Use for the single primary action per screen.
- `secondary` — navy raised background. Default for most actions.
- `ghost` — transparent, hover highlight. Use in toolbars and nav.
- `danger` — red, used for destructive actions (delete, cancel).
- `outline` — bordered, no background.

---

### Input

```tsx
<Input
  label="Experiment ID"
  placeholder="e.g. HPHT_001"
  error={errors.experimentId}
  hint="Must be unique"
/>
```

| Prop | Type | Description |
|------|------|-------------|
| `label` | `string` | Field label |
| `error` | `string` | Error message (red border + text) |
| `hint` | `string` | Helper text below input |
| `leftIcon` | `ReactNode` | Icon in left slot |
| `rightElement` | `ReactNode` | Element in right slot |

Extends all `<input>` HTML attributes. IDs are generated via `useId()`.

---

### Select

```tsx
<Select
  label="Status"
  options={[
    { value: 'ONGOING', label: 'Ongoing' },
    { value: 'COMPLETED', label: 'Completed' },
  ]}
  error={errors.status}
/>
```

| Prop | Type | Description |
|------|------|-------------|
| `label` | `string` | Field label |
| `options` | `{ value: string; label: string; disabled?: boolean }[]` | Options list |
| `error` | `string` | Error message |
| `placeholder` | `string` | Unselected label |
| `leftIcon` | `ReactNode` | Icon in left slot |

---

### Card

```tsx
<Card variant="raised" padding="md">
  <CardHeader label="Conditions" />
  <CardBody>…</CardBody>
</Card>

<MetricCard label="H₂ Yield" value="142.3" unit="g/t" trend="up" />
```

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `variant` | `'default' \| 'raised' \| 'flat'` | `'default'` | Shadow depth |
| `padding` | `'none' \| 'sm' \| 'md' \| 'lg'` | `'md'` | |

`MetricCard` props: `label`, `value`, `unit?`, `sub?`, `trend?: 'up' | 'down' | 'neutral'`.

---

### Badge / StatusBadge

```tsx
<Badge variant="success">Active</Badge>
<StatusBadge status="ONGOING" />  {/* auto-maps status → variant */}
```

| Prop | Type | Default |
|------|------|---------|
| `variant` | `'default' \| 'success' \| 'warning' \| 'error' \| 'info' \| 'ongoing' \| 'completed' \| 'cancelled'` | `'default'` |
| `dot` | `boolean` | `false` |

`StatusBadge` accepts a `status` string and maps it to the correct variant automatically.

---

### Table

```tsx
<Table striped>
  <TableHead>
    <TableRow>
      <Th>Experiment ID</Th>
      <Th>Status</Th>
      <Th>H₂ Yield</Th>
    </TableRow>
  </TableHead>
  <TableBody>
    {rows.map((row) => (
      <TableRow key={row.id}>
        <Td>{row.experiment_id}</Td>
        <Td><StatusBadge status={row.status} /></Td>
        <TdValue>{row.h2_yield}</TdValue>
      </TableRow>
    ))}
  </TableBody>
</Table>
```

`TdValue` is right-aligned and uses `font-mono-data`. Use it for all numeric columns.

---

### Modal / ConfirmModal

```tsx
<Modal open={open} onClose={() => setOpen(false)} title="Edit Sample" size="md">
  {/* content */}
</Modal>

<ConfirmModal
  open={open}
  onClose={() => setOpen(false)}
  onConfirm={handleDelete}
  title="Delete experiment?"
  description="This cannot be undone."
  confirmLabel="Delete"
  danger
/>
```

`Modal` sizes: `'sm' | 'md' | 'lg' | 'xl'`. Closes on Escape key or backdrop click.

---

### Toast

```tsx
const toast = useToast()

toast.success('Saved')
toast.error('Failed to save', err.message)
toast.warning('Partial upload')
toast.info('Recalculating...')
```

`ToastProvider` is mounted in `main.tsx`. Auto-dismisses after 5 seconds. Fixed bottom-right.

---

### Spinner / PageSpinner

```tsx
<Spinner size="sm" />
<PageSpinner />  {/* full-height centered loading state */}
```

Use `PageSpinner` as the loading state for whole-page query loading. Use `Spinner` inline (e.g. inside a Button via the `loading` prop, or in a table cell).

---

### FileUpload

```tsx
<FileUpload
  accept=".xlsx,.csv"
  onFiles={(files) => handleUpload(files)}
  label="Drop scalar results file here"
  hint="Accepts .xlsx or .csv"
  error={uploadError}
/>
```

| Prop | Type | Description |
|------|------|-------------|
| `accept` | `string` | MIME types or extensions |
| `multiple` | `boolean` | Allow multi-file selection |
| `onFiles` | `(files: File[]) => void` | Called on drop or click-select |
| `label` | `string` | Zone label |
| `hint` | `string` | Helper text |
| `error` | `string` | Error message |

---

## Adding a New Component

1. Create `src/components/ui/MyComponent.tsx`.
2. Export a typed props interface: `export interface MyComponentProps extends React.HTMLAttributes<HTMLDivElement> { ... }`.
3. Use only Tailwind utility classes — no inline `style={{ color: '#...' }}`.
4. Reference brand colors via Tailwind (e.g. `text-ink-primary`, `bg-navy-raised`). Never hardcode hex.
5. Use `useId()` for any `id` or `htmlFor` attributes that need stable, unique values.
6. Add the export to `src/components/ui/index.ts`.

```ts
// index.ts
export { MyComponent } from './MyComponent'
export type { MyComponentProps } from './MyComponent'
```
