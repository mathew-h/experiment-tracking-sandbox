/**
 * Journey 2 — Additives edit/delete
 *
 * Creates an experiment, adds a chemical additive, verifies the edit button
 * is accessible (via aria-label), edits the additive, then deletes it via
 * the confirmation modal.
 *
 * Notes on selectors (verified against ConditionsTab.tsx):
 * - Compound search input placeholder: "Search compounds…" (Unicode ellipsis)
 * - Add/Edit additive modal submit button: "Save" (both modals use the same label)
 * - Edit button aria-label: "Edit additive"
 * - Delete button aria-label: "Delete additive"
 * - Delete confirmation modal title: "Remove additive?"
 * - Delete confirmation confirm button: "Remove"
 *
 * Tests run in serial order. Test state is intentionally cumulative:
 * the additive added in test 2 persists for tests 3 and 4.
 * Test 5 re-adds the additive after test 4 deletes it.
 */
import { test, expect } from '../fixtures/auth'

// Shared experiment ID — set once by the first test, reused by the rest.
// Using a module-level variable; tests in this describe block run serially
// via test.describe.configure({ mode: 'serial' }).
let expId: string

test.describe('Additives edit/delete', () => {
  test.describe.configure({ mode: 'serial' })

  test('setup: create experiment', async ({ page }) => {
    await page.goto('/experiments/new')
    await page.getByLabel(/experiment type/i).selectOption('Serum')
    const idInput = page.getByLabel(/experiment id/i)
    await expect(idInput).not.toHaveValue(/loading/i, { timeout: 10_000 })
    await expect(idInput).not.toHaveValue('', { timeout: 10_000 })
    expId = await idInput.inputValue()
    await page.getByRole('button', { name: /next.*condition/i }).click()
    await page.getByLabel(/rock mass/i).fill('5')
    await page.getByLabel(/water volume/i).fill('50')
    await page.getByRole('button', { name: /next.*additive/i }).click()
    await page.getByRole('button', { name: /next.*review/i }).click()
    await page.getByRole('button', { name: /create experiment/i }).click()
    await expect(page).not.toHaveURL(/\/experiments\/new/, { timeout: 15_000 })
  })

  test('edit button is visible and has correct aria-label', async ({ page }) => {
    await page.goto('/experiments')
    await page.getByText(expId).first().click()

    // Add an additive so there is something to edit
    await page.getByRole('button', { name: /\+ add/i }).click()
    await page.getByPlaceholder(/search compounds/i).fill('Magnetite')
    await page.getByText('Magnetite').first().click()
    await page.getByLabel(/amount/i).fill('2')
    // The modal submit button is labelled "Save" in both Add and Edit modals
    await page.getByRole('button', { name: /^save$/i }).click()
    await expect(page.getByText('Magnetite')).toBeVisible({ timeout: 8_000 })

    // Hover the additive row to reveal the action buttons
    const row = page.locator('div.group').filter({ hasText: 'Magnetite' }).first()
    await row.hover()

    const editBtn = row.getByRole('button', { name: /edit additive/i })
    await expect(editBtn).toBeVisible({ timeout: 5_000 })
  })

  test('edit flow opens modal and saves updated amount', async ({ page }) => {
    await page.goto(`/experiments/${expId}`)

    const row = page.locator('div.group').filter({ hasText: 'Magnetite' }).first()
    await row.hover()
    await row.getByRole('button', { name: /edit additive/i }).click()

    // Edit modal should be open — change amount
    const amountInput = page.getByLabel(/amount/i)
    await amountInput.clear()
    await amountInput.fill('10')
    await page.getByRole('button', { name: /^save$/i }).click()

    await expect(row.getByText('10')).toBeVisible({ timeout: 5_000 })
  })

  test('delete button triggers confirmation modal and removes additive', async ({ page }) => {
    await page.goto(`/experiments/${expId}`)

    const row = page.locator('div.group').filter({ hasText: 'Magnetite' }).first()
    await row.hover()
    await row.getByRole('button', { name: /delete additive/i }).click()

    // Confirmation modal must appear (ConfirmModal title: "Remove additive?")
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 3_000 })
    await expect(page.getByText(/remove additive/i)).toBeVisible()

    // Confirm deletion (confirmLabel="Remove" on the ConfirmModal)
    await page.getByRole('button', { name: /^remove$/i }).click()

    // Additive should be gone
    await expect(page.getByText('Magnetite')).not.toBeVisible({ timeout: 5_000 })
  })

  test('cancel on confirmation modal does not remove additive', async ({ page }) => {
    // Re-add the additive so we can cancel its deletion
    await page.goto(`/experiments/${expId}`)
    await page.getByRole('button', { name: /\+ add/i }).click()
    await page.getByPlaceholder(/search compounds/i).fill('Magnetite')
    await page.getByText('Magnetite').first().click()
    await page.getByLabel(/amount/i).fill('3')
    await page.getByRole('button', { name: /^save$/i }).click()
    await expect(page.getByText('Magnetite')).toBeVisible({ timeout: 8_000 })

    const row = page.locator('div.group').filter({ hasText: 'Magnetite' }).first()
    await row.hover()
    await row.getByRole('button', { name: /delete additive/i }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByRole('button', { name: /cancel/i }).click()

    // Additive still present
    await expect(page.getByText('Magnetite')).toBeVisible()
  })
})
