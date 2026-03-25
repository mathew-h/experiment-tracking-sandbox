/**
 * Journey 12 — Chemicals page and chemical additive flows
 *
 * Covers:
 *   1. Chemicals page: add a new compound (full form), verify it appears in table
 *   2. Chemicals page: search filters the compound list
 *   3. Chemicals page: edit an existing compound (supplier field)
 *   4. Experiment conditions tab: add a chemical additive via inline "Create" flow
 *   5. Experiment conditions tab: delete a chemical additive
 *
 * Each test is fully independent: it creates its own test data via a local suffix
 * (Date.now() evaluated inside the test, not at module level, to avoid sharing
 * state across tests in Playwright's per-test module evaluation).
 *
 * Note: The Modal component renders as a plain <div> overlay (no role="dialog"),
 * so open/closed state is detected via the modal's title <h2> heading.
 *
 * Note: After a successful mutation, a toast notification appears containing
 * the compound name. To avoid strict-mode violations from getByText() matching
 * both the table cell and the toast, we target table cells specifically.
 */
import { test, expect } from '../fixtures/auth'

// ── 1. Add compound via Chemicals page ─────────────────────────────────────

test('add new compound on chemicals page and verify it appears in table', async ({ page }) => {
  const suffix = Date.now().toString().slice(-6)
  const COMPOUND_NAME = `E2E Add ${suffix}`
  const COMPOUND_FORMULA = `E2EF${suffix}`

  await page.goto('/chemicals')
  await expect(page.getByRole('heading', { name: 'Chemicals' })).toBeVisible({ timeout: 10_000 })

  // Open the Add Compound modal
  await page.getByRole('button', { name: /add compound/i }).click()

  // Modal open = its h2 title is visible
  const modalTitle = page.getByRole('heading', { name: 'Add Compound' })
  await expect(modalTitle).toBeVisible({ timeout: 5_000 })

  // Fill fields
  await page.getByLabel('Name *').fill(COMPOUND_NAME)
  await page.getByLabel('Formula').fill(COMPOUND_FORMULA)
  await page.getByLabel('Supplier').fill('Sigma-Aldrich')

  // Submit
  await page.getByRole('button', { name: 'Create Compound' }).click()

  // Modal closes (heading disappears)
  await expect(modalTitle).not.toBeVisible({ timeout: 8_000 })

  // Compound appears in the table — target the cell specifically to avoid
  // matching the toast notification that also contains the compound name
  await expect(
    page.getByRole('cell').filter({ hasText: COMPOUND_NAME })
  ).toBeVisible({ timeout: 8_000 })

  // Formula column also present
  await expect(
    page.getByRole('cell').filter({ hasText: COMPOUND_FORMULA })
  ).toBeVisible()
})

// ── 2. Search filters the compound list ────────────────────────────────────

test('search filters compounds on chemicals page', async ({ page }) => {
  const suffix = Date.now().toString().slice(-6)
  const COMPOUND_NAME = `E2E Search ${suffix}`

  await page.goto('/chemicals')
  await expect(page.getByRole('heading', { name: 'Chemicals' })).toBeVisible({ timeout: 10_000 })

  // First create a compound so we can search for it
  await page.getByRole('button', { name: /add compound/i }).click()
  const modalTitle = page.getByRole('heading', { name: 'Add Compound' })
  await expect(modalTitle).toBeVisible({ timeout: 5_000 })
  await page.getByLabel('Name *').fill(COMPOUND_NAME)
  await page.getByRole('button', { name: 'Create Compound' }).click()
  await expect(modalTitle).not.toBeVisible({ timeout: 8_000 })
  await expect(page.getByRole('cell').filter({ hasText: COMPOUND_NAME })).toBeVisible({ timeout: 8_000 })

  // Search by exact name — our compound should remain visible
  await page.getByPlaceholder('Search compounds…').fill(COMPOUND_NAME)
  await expect(page.getByRole('cell').filter({ hasText: COMPOUND_NAME })).toBeVisible({ timeout: 8_000 })

  // Searching for something that doesn't exist shows "No compounds found"
  await page.getByPlaceholder('Search compounds…').fill('zzz_no_match_xyz')
  await expect(page.getByText('No compounds found')).toBeVisible({ timeout: 8_000 })

  // Clearing the search brings the list back
  await page.getByPlaceholder('Search compounds…').fill('')
  await expect(page.getByRole('cell').filter({ hasText: COMPOUND_NAME })).toBeVisible({ timeout: 8_000 })
})

// ── 3. Edit an existing compound ───────────────────────────────────────────

test('edit existing compound supplier via chemicals page', async ({ page }) => {
  const suffix = Date.now().toString().slice(-6)
  const COMPOUND_NAME = `E2E Edit ${suffix}`

  await page.goto('/chemicals')
  await expect(page.getByRole('heading', { name: 'Chemicals' })).toBeVisible({ timeout: 10_000 })

  // Create a compound to edit
  await page.getByRole('button', { name: /add compound/i }).click()
  const addModalTitle = page.getByRole('heading', { name: 'Add Compound' })
  await expect(addModalTitle).toBeVisible({ timeout: 5_000 })
  await page.getByLabel('Name *').fill(COMPOUND_NAME)
  await page.getByLabel('Supplier').fill('Sigma-Aldrich')
  await page.getByRole('button', { name: 'Create Compound' }).click()
  await expect(addModalTitle).not.toBeVisible({ timeout: 8_000 })
  await expect(page.getByRole('cell').filter({ hasText: COMPOUND_NAME })).toBeVisible({ timeout: 8_000 })

  // Narrow results by searching, then click Edit
  await page.getByPlaceholder('Search compounds…').fill(COMPOUND_NAME)
  await expect(page.getByRole('cell').filter({ hasText: COMPOUND_NAME })).toBeVisible({ timeout: 5_000 })

  const row = page.getByRole('row').filter({ hasText: COMPOUND_NAME })
  await row.getByRole('button', { name: 'Edit' }).click()

  // Edit modal opens pre-filled
  const editModalTitle = page.getByRole('heading', { name: `Edit: ${COMPOUND_NAME}` })
  await expect(editModalTitle).toBeVisible({ timeout: 5_000 })
  await expect(page.getByLabel('Name *')).toHaveValue(COMPOUND_NAME)
  await expect(page.getByLabel('Supplier')).toHaveValue('Sigma-Aldrich')

  // Update supplier
  await page.getByLabel('Supplier').fill('Fisher Scientific')
  await page.getByRole('button', { name: 'Save Changes' }).click()

  // Modal closes
  await expect(editModalTitle).not.toBeVisible({ timeout: 8_000 })

  // Updated supplier visible in table row
  await expect(
    page.getByRole('row').filter({ hasText: COMPOUND_NAME }).getByText('Fisher Scientific')
  ).toBeVisible({ timeout: 8_000 })
})

// ── 4 & 5. Additive flow on experiment conditions tab ──────────────────────

test('add and remove chemical additive on experiment conditions tab', async ({ page }) => {
  const suffix = Date.now().toString().slice(-6)
  const INLINE_COMPOUND_NAME = `E2E Additive ${suffix}`

  // ── Create a minimal experiment ──────────────────────────────────────
  await page.goto('/experiments/new')

  await page.getByLabel(/experiment type/i).selectOption('HPHT')

  const idInput = page.getByLabel(/experiment id/i)
  await expect(idInput).not.toHaveValue(/loading/i, { timeout: 10_000 })
  await expect(idInput).not.toHaveValue('', { timeout: 10_000 })
  const expId = await idInput.inputValue()

  await page.getByRole('button', { name: /next.*condition/i }).click()
  await page.getByLabel(/rock mass/i).fill('5')
  await page.getByLabel(/water volume/i).fill('50')
  await page.getByRole('button', { name: /next.*additive/i }).click()
  await page.getByRole('button', { name: /next.*review/i }).click()
  await page.getByRole('button', { name: /create experiment/i }).click()
  await expect(page).not.toHaveURL(/\/experiments\/new/, { timeout: 15_000 })

  // ── Navigate to the experiment's Conditions tab ───────────────────────
  await page.goto('/experiments')
  await page.getByText(expId).first().click()
  await expect(page.getByText('Chemical Additives')).toBeVisible({ timeout: 10_000 })

  // ── Open Add Chemical Additive modal ──────────────────────────────────
  await page.getByRole('button', { name: '+ Add' }).click()

  const addAdditiveHeading = page.getByRole('heading', { name: 'Add Chemical Additive' })
  await expect(addAdditiveHeading).toBeVisible({ timeout: 5_000 })

  // ── Type compound name and choose inline "Create" option ──────────────
  await page.getByPlaceholder('Search compounds…').last().fill(INLINE_COMPOUND_NAME)

  const createOption = page.getByRole('button', {
    name: new RegExp(`Create "${INLINE_COMPOUND_NAME}"`, 'i'),
  })
  await expect(createOption).toBeVisible({ timeout: 6_000 })
  await createOption.click()

  // Minimal CompoundFormModal opens pre-filled with the name
  const createCompoundHeading = page.getByRole('heading', { name: 'Add Compound' })
  await expect(createCompoundHeading).toBeVisible({ timeout: 5_000 })
  await expect(page.getByLabel('Name *')).toHaveValue(INLINE_COMPOUND_NAME)

  // Submit the minimal create
  await page.getByRole('button', { name: 'Create Compound' }).click()

  // CompoundFormModal closes; back to Add Chemical Additive modal
  await expect(createCompoundHeading).not.toBeVisible({ timeout: 8_000 })
  await expect(addAdditiveHeading).toBeVisible()

  // The selected compound name is shown in the modal's "selected" display span.
  // Scope to the modal overlay to avoid matching the toast notification.
  const modalOverlay = page.locator('.fixed.inset-0').last()
  await expect(
    modalOverlay.getByText(INLINE_COMPOUND_NAME, { exact: true })
  ).toBeVisible({ timeout: 5_000 })

  // Fill amount and save (unit defaults to 'g')
  await page.getByLabel('Amount').fill('2.5')
  await page.getByRole('button', { name: /^save$/i }).last().click()

  // Modal closes
  await expect(addAdditiveHeading).not.toBeVisible({ timeout: 8_000 })

  // ── Verify additive row appears in the conditions tab ────────────────
  // Use the div.group locator (the actual additive row) rather than getByText,
  // to avoid matching the "Compound created" toast which also contains the name.
  const additiveRow = page.locator('div.group').filter({ hasText: INLINE_COMPOUND_NAME })
  await expect(additiveRow).toBeVisible({ timeout: 8_000 })
  await expect(page.getByText(/2\.5\s*g/)).toBeVisible()

  // ── Delete the additive ────────────────────────────────────────────────
  await additiveRow.hover()

  // × button reveals on hover via opacity transition
  const deleteBtn = additiveRow.getByRole('button')
  await expect(deleteBtn).toBeVisible({ timeout: 3_000 })
  await deleteBtn.click()

  // The div.group row disappears (toast may still show compound name briefly,
  // but it is not inside a div.group so this check is unambiguous)
  await expect(additiveRow).not.toBeVisible({ timeout: 8_000 })
})
