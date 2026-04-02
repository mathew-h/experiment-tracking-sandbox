/**
 * Journey 3 — Notes edit/delete
 *
 * Creates an experiment, navigates to the Notes tab, adds a note, edits it,
 * then deletes it. Verifies the confirmation modal gates deletion.
 *
 * Notes on selectors (verified against NotesTab.tsx and ExperimentDetail/index.tsx):
 * - The Notes tab is a plain <button> element (NOT role="tab") — use getByRole('button')
 * - Add-note textarea placeholder: "Add a note…" (Unicode ellipsis)
 * - Add note submit button text: "Add Note" (capital N)
 * - Edit button aria-label: "Edit note"
 * - Delete button aria-label: "Delete note"
 * - Delete confirmation modal title: "Delete note?"
 * - Delete confirmation confirm button: "Delete" (confirmLabel="Delete")
 *
 * Tests run in serial order. Test state is intentionally cumulative:
 * the note added in test 2 persists for tests 3 and 4.
 * Test 5 re-adds a note after test 4 deletes it.
 */
import { test, expect } from '../fixtures/auth'

// Shared experiment ID — set once by the first test, reused by the rest.
// Using a module-level variable; tests in this describe block run serially
// via test.describe.configure({ mode: 'serial' }).
let expId: string

test.describe('Notes edit/delete', () => {
  test.describe.configure({ mode: 'serial' })

  test('setup: create experiment', async ({ page }) => {
    await page.goto('/experiments/new')
    await page.getByLabel(/experiment type/i).selectOption('Autoclave')
    const idInput = page.getByLabel(/experiment id/i)
    await expect(idInput).not.toHaveValue(/loading/i, { timeout: 10_000 })
    await expect(idInput).not.toHaveValue('', { timeout: 10_000 })
    expId = await idInput.inputValue()
    await page.getByRole('button', { name: /next.*condition/i }).click()
    await page.getByRole('button', { name: /next.*additive/i }).click()
    await page.getByRole('button', { name: /next.*review/i }).click()
    await page.getByRole('button', { name: /create experiment/i }).click()
    await expect(page).not.toHaveURL(/\/experiments\/new/, { timeout: 15_000 })
  })

  test('edit button is accessible via aria-label', async ({ page }) => {
    await page.goto(`/experiments/${expId}`)

    // Notes tab is a plain <button>, not role="tab" — match exact label text
    await page.getByRole('button', { name: /^Notes/ }).click()

    // Add a note so there is something to interact with
    await page.getByPlaceholder(/add a note/i).fill('Initial observation')
    await page.getByRole('button', { name: /^add note$/i }).click()
    await expect(page.getByText('Initial observation')).toBeVisible({ timeout: 5_000 })

    // Hover the note row to reveal action buttons (opacity-0 group-hover:opacity-100)
    const noteRow = page.locator('div.group').filter({ hasText: 'Initial observation' }).first()
    await noteRow.hover()

    await expect(noteRow.getByRole('button', { name: /^edit note$/i })).toBeVisible({ timeout: 3_000 })
    await expect(noteRow.getByRole('button', { name: /^delete note$/i })).toBeVisible({ timeout: 3_000 })
  })

  test('edit flow opens inline editor and saves updated text', async ({ page }) => {
    await page.goto(`/experiments/${expId}`)

    // Navigate to Notes tab
    await page.getByRole('button', { name: /^Notes/ }).click()

    const noteRow = page.locator('div.group').filter({ hasText: 'Initial observation' }).first()
    await noteRow.hover()
    await noteRow.getByRole('button', { name: /^edit note$/i }).click()

    // Inline editor textarea should appear inside the note row
    const textarea = noteRow.locator('textarea')
    await expect(textarea).toBeVisible()
    await textarea.clear()
    await textarea.fill('Updated observation')

    // Save button inside the inline editor row
    await noteRow.getByRole('button', { name: /^save$/i }).click()

    await expect(page.getByText('Updated observation')).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText('Initial observation')).not.toBeVisible()
  })

  test('delete button triggers confirmation modal and removes note', async ({ page }) => {
    await page.goto(`/experiments/${expId}`)
    await page.getByRole('button', { name: /^Notes/ }).click()

    const noteRow = page.locator('div.group').filter({ hasText: 'Updated observation' }).first()
    await noteRow.hover()
    await noteRow.getByRole('button', { name: /^delete note$/i }).click()

    // Confirmation modal must appear (ConfirmModal title: "Delete note?")
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 3_000 })
    await expect(page.getByText(/delete note\?/i)).toBeVisible()

    // Confirm deletion (confirmLabel="Delete" on the ConfirmModal)
    await page.getByRole('button', { name: /^delete$/i }).click()

    // Note should be gone
    await expect(page.getByText('Updated observation')).not.toBeVisible({ timeout: 5_000 })
  })

  test('cancel on confirmation modal preserves the note', async ({ page }) => {
    await page.goto(`/experiments/${expId}`)
    await page.getByRole('button', { name: /^Notes/ }).click()

    // Add a fresh note to cancel-test against
    await page.getByPlaceholder(/add a note/i).fill('Note to keep')
    await page.getByRole('button', { name: /^add note$/i }).click()
    await expect(page.getByText('Note to keep')).toBeVisible({ timeout: 5_000 })

    const noteRow = page.locator('div.group').filter({ hasText: 'Note to keep' }).first()
    await noteRow.hover()
    await noteRow.getByRole('button', { name: /^delete note$/i }).click()
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 3_000 })

    // Cancel — note must still be visible
    await page.getByRole('button', { name: /cancel/i }).click()

    await expect(page.getByText('Note to keep')).toBeVisible()
  })
})
