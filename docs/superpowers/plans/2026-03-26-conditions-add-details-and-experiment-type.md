# Conditions Tab: Add Details Button + Experiment Type Field Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to add conditions to an experiment that was created without them, and set/change the experiment type from the UI.

**Architecture:** Two-file frontend change. `ConditionsTab` gains a `experimentFk` prop, a unified `saveMutation` (create vs patch), an empty-state UI, and an `experiment_type` dropdown in the form modal. `index.tsx` passes the new prop. No backend or schema changes needed — `conditionsApi.create` and the `experiment_type` field already exist.

**Tech Stack:** React 18, TypeScript, React Query (`useMutation`, `useQueryClient`), Tailwind CSS, existing `conditionsApi`, `Button`, `Modal`, `Select` UI components.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx` | All logic + JSX changes |
| Modify | `frontend/src/pages/ExperimentDetail/index.tsx` | Pass `experimentFk` prop to `ConditionsTab` |

No new files. No backend changes.

---

## Task 1: Add `experimentFk` prop and wire `saveMutation`

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx`
- Modify: `frontend/src/pages/ExperimentDetail/index.tsx`

This task wires up the data layer before touching any UI. By the end, saving via the existing "Edit" button will still work, plus a create path is plumbed in.

- [ ] **Step 1: Add `experimentFk` to the Props interface**

In `ConditionsTab.tsx`, find:
```ts
interface Props {
  conditions: ConditionsResponse | null
  experimentId: string
}
```
Replace with:
```ts
interface Props {
  conditions: ConditionsResponse | null
  experimentId: string
  experimentFk: number
}
```

Update the function signature:
```ts
export function ConditionsTab({ conditions, experimentId, experimentFk }: Props) {
```

- [ ] **Step 2: Replace `patchMutation` with `saveMutation`**

Find the entire `patchMutation` block:
```ts
const patchMutation = useMutation({
  mutationFn: () => {
    if (!conditions) throw new Error('No conditions to patch')
    return conditionsApi.patch(conditions.id, form)
  },
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })
    queryClient.invalidateQueries({ queryKey: ['conditions', experimentId] })
    success('Conditions updated')
    setEditOpen(false)
  },
  onError: (err: Error) => toastError('Update failed', err.message),
})
```

Replace with:
```ts
const saveMutation = useMutation({
  mutationFn: () => {
    if (!conditions) {
      return conditionsApi.create({
        experiment_fk: experimentFk,
        experiment_id: experimentId,
        ...form,
      })
    }
    return conditionsApi.patch(conditions.id, form)
  },
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })
    queryClient.invalidateQueries({ queryKey: ['conditions', experimentId] })
    success(conditions ? 'Conditions updated' : 'Details added')
    setEditOpen(false)
  },
  onError: (err: Error) =>
    toastError(conditions ? 'Update failed' : 'Failed to add details', err.message),
})
```

- [ ] **Step 3: Update all references from `patchMutation` → `saveMutation`**

In the Edit Conditions Modal Save button (near bottom of file), replace:
```tsx
<Button variant="primary" loading={patchMutation.isPending} onClick={() => patchMutation.mutate()}>Save</Button>
```
with:
```tsx
<Button variant="primary" loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>Save</Button>
```

- [ ] **Step 4: Pass `experimentFk` from `index.tsx`**

In `frontend/src/pages/ExperimentDetail/index.tsx`, find:
```tsx
<ConditionsTab conditions={conditions ?? null} experimentId={id!} />
```
Replace with:
```tsx
<ConditionsTab conditions={conditions ?? null} experimentId={id!} experimentFk={experiment.id} />
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors. If there are errors, fix them before proceeding.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/ConditionsTab.tsx \
        frontend/src/pages/ExperimentDetail/index.tsx
git commit -m "feat: add experimentFk prop and saveMutation"
```

---

## Task 2: Replace early return with empty state UI

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx`

Currently `ConditionsTab` bails out early when `conditions` is null, which means no modals render. This task removes that early return and restructures the JSX so the Edit modal is always available, but the main body is conditional.

> **Important:** Two helpers — `set` and `hasExactCompoundMatch` — are currently defined *after* the early return (lines ~144–149). They are referenced inside the modal JSX. After removing the early return they must live *before* `return (` or TypeScript will error. Step 1 handles this.

- [ ] **Step 1: Move `set` and `hasExactCompoundMatch` above `return (`**

Find these two declarations (currently just before `return (`):
```ts
const set = (k: keyof ConditionsPayload) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
  setForm((p) => ({ ...p, [k]: e.target.value === '' ? undefined : (isNaN(Number(e.target.value)) ? e.target.value : Number(e.target.value)) }))

const hasExactCompoundMatch = compoundResults.some(
  (c: Compound) => c.name.toLowerCase() === compoundQuery.toLowerCase()
)
```

These are currently placed after the early return. After removing the early return in Step 2, they will still be before `return (` — **no move is needed if you remove the early return first**. However, if your editor flags them as unreachable before you remove the early return, delete the early return line before touching anything else.

- [ ] **Step 2: Remove the early return**

Find and delete this single line:
```tsx
if (!conditions) return <p className="text-sm text-ink-muted p-4">No conditions recorded for this experiment.</p>
```

After deletion, `set` and `hasExactCompoundMatch` will be above `return (` — correct position.

- [ ] **Step 3: Wrap the conditions display block in a conditional**

The ternary uses `!conditions` — empty state when null, full view when present. Both modals (Edit Conditions + Add Additive) must stay **outside** the ternary so they render in both states.

Replace the opening of the return statement from:
```tsx
  return (
    <>
      <div className="p-4 space-y-1">
```
with:
```tsx
  return (
    <>
      {!conditions ? (
        <div className="p-8 flex flex-col items-center gap-3 text-center">
          <p className="text-sm text-ink-muted">No conditions recorded for this experiment.</p>
          <Button variant="ghost" size="sm" onClick={openEdit}>+ Add Details</Button>
        </div>
      ) : (
        <div className="p-4 space-y-1">
```

- [ ] **Step 4: Close the ternary before the Edit Conditions Modal**

The ternary wraps only the conditions display `<div>` and the Chemical Additives `<div>`. Close it just before `{/* Edit Conditions Modal */}`.

Find the end of the Chemical Additives block — the closing `</div>` just before the `{/* Edit Conditions Modal */}` comment:
```tsx
      </div>

      {/* Edit Conditions Modal */}
```
Replace with:
```tsx
        </div>
      )}

      {/* Edit Conditions Modal */}
```

> **Structure check after this change:**
> ```
> <>
>   {!conditions ? (               ← empty state branch
>     <div p-8>...</div>
>   ) : (                          ← full view branch
>     <>
>       <div p-4>...</div>         ← conditions rows
>       <div px-4>...</div>        ← chemical additives
>     </>
>   )}
>   <Modal editOpen>...</Modal>          ← OUTSIDE ternary ✓
>   <Modal addAdditiveOpen>...</Modal>   ← OUTSIDE ternary ✓
> </>
> ```
> Confirm the Add Additive Modal (`{/* Add Additive Modal */}`, lines ~241–343) is still after the `)}` — not accidentally indented inside the ternary.

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 6: Manual smoke test**

Start the dev server if not running (`npm run dev`). Navigate to an experiment that has NO conditions. Confirm:
- Empty state text and "+ Add Details" button appear
- Clicking the button opens the modal
- Clicking Cancel closes it with no error

Navigate to an experiment that HAS conditions. Confirm:
- The normal conditions view renders
- "Edit" button still works
- "+ Add" (additive) button still works

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/ConditionsTab.tsx
git commit -m "feat: empty state with Add Details button"
```

---

## Task 3: Add `experiment_type` dropdown to the form modal

**Files:**
- Modify: `frontend/src/pages/ExperimentDetail/ConditionsTab.tsx`

`experiment_type` is already in `ConditionsPayload` and `ConditionsResponse`. It just needs a form field and inclusion in `openEdit`.

- [ ] **Step 1: Add the options constant**

Near the top of the file (alongside `FEEDSTOCK_OPTIONS` and `ADDITIVE_UNIT_OPTIONS`), add:
```ts
const EXPERIMENT_TYPE_OPTIONS = [
  { value: 'Serum',      label: 'Serum' },
  { value: 'Autoclave',  label: 'Autoclave' },
  { value: 'HPHT',       label: 'HPHT' },
  { value: 'Core Flood', label: 'Core Flood' },
  { value: 'Other',      label: 'Other' },
]
```

- [ ] **Step 2: Initialise `experiment_type` in `openEdit`**

Find `openEdit`:
```ts
const openEdit = () => {
  setForm({
    temperature_c: conditions?.temperature_c ?? undefined,
    ...
  })
  setEditOpen(true)
}
```

Add `experiment_type` to the `setForm` call:
```ts
experiment_type: conditions?.experiment_type ?? undefined,
```

Place it as the first field in the object for readability.

- [ ] **Step 3: Add the `Select` to the edit modal grid**

Inside the Edit Conditions Modal, find the `<div className="grid grid-cols-2 gap-3">`. Add as the **first** field in the grid:
```tsx
<Select
  label="Experiment Type"
  options={EXPERIMENT_TYPE_OPTIONS}
  value={form.experiment_type ?? ''}
  onChange={(e) => setForm((p) => ({ ...p, experiment_type: e.target.value || undefined }))}
  placeholder="Select type…"
/>
```

This sits at grid position [0,0] so it appears top-left, before Particle Size.

> **Type note:** `experiment_type` is typed as `string | undefined` in `ConditionsPayload` (not an enum), so assigning `e.target.value` (a plain string) requires no cast. TypeScript will not error here.

- [ ] **Step 4: Update the modal title to reflect create vs edit**

Find the Edit Conditions Modal `<Modal ... title="Edit Conditions">` and replace with:
```tsx
<Modal open={editOpen} onClose={() => setEditOpen(false)} title={conditions ? 'Edit Conditions' : 'Add Details'}>
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 6: Manual smoke test — experiment_type flow**

1. Open an experiment with NO conditions → click "+ Add Details"
2. Confirm "Experiment Type" dropdown appears as the first field
3. Select "Core Flood", set Reactor # to `1`, click Save
4. Confirm the conditions panel now shows "Type: Core Flood" and "Reactor: 1"
5. Navigate to the Reactor Dashboard — confirm the experiment appears on **CF01**

6. Open an experiment WITH conditions → click "Edit"
7. Confirm "Experiment Type" dropdown is pre-populated with the current value
8. Change it and save — confirm the displayed Type updates

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ExperimentDetail/ConditionsTab.tsx
git commit -m "feat: add experiment_type dropdown to conditions add/edit modal"
```

---

## Final verification checklist

Before calling the branch complete, confirm all acceptance criteria:

- [ ] Experiment with no conditions → empty state + "+ Add Details" button visible
- [ ] Clicking "+ Add Details" → modal opens titled "Add Details"
- [ ] Saving → calls `POST /api/conditions`, conditions panel appears, cache invalidated
- [ ] Experiment with existing conditions → "Edit" button visible, modal titled "Edit Conditions"
- [ ] `experiment_type` dropdown present in both Add and Edit modals
- [ ] Selecting "Core Flood" + saving → "Type: Core Flood" shown in conditions panel
- [ ] Setting reactor_number=1, experiment_type=Core Flood on ONGOING experiment → CF01 card occupied in Reactor Dashboard
- [ ] `npx tsc --noEmit` — zero errors
- [ ] `npx eslint src --ext .ts,.tsx` — zero warnings
