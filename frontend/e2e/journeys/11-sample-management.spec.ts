/**
 * Journey 11 — M9 Sample Management
 *
 * Covers: sample inventory list, characterized sample detail (regression for
 * experiment_type.value 500 bug), sample editor (PATCH), new sample modal,
 * and rock inventory bulk upload.
 *
 * Regression sample IDs (characterized=True, many linked experiments):
 *   - 20250212_2A  (103 experiments)
 *   - 20250529_2C  (23 experiments)
 */
import { test, expect } from '../fixtures/auth'
import * as path from 'path'
import * as url from 'url'

const __dirname = path.dirname(url.fileURLToPath(import.meta.url))
const ROCK_INVENTORY_FIXTURE = path.resolve(__dirname, '../fixtures/rock_inventory_fixture.xlsx')

// ── Sample list ──────────────────────────────────────────────────────────────

test('sample inventory page loads and shows samples', async ({ page }) => {
  await page.goto('/samples')
  await expect(page.getByRole('heading', { name: /samples/i })).toBeVisible()
  // Total count badge appears once the list loads
  await expect(page.getByText(/\d+ samples/)).toBeVisible({ timeout: 10_000 })
  // Table has at least one data row
  await expect(page.locator('tbody tr').first()).toBeVisible()
})

test('sample list search filter narrows results', async ({ page }) => {
  await page.goto('/samples')
  await expect(page.locator('tbody tr').first()).toBeVisible({ timeout: 10_000 })

  const searchInput = page.getByPlaceholder(/search by id or description/i)
  await searchInput.fill('20250212')
  // Results should narrow — at least the exact sample should appear
  await expect(page.getByText('20250212_2A')).toBeVisible({ timeout: 8_000 })
})

test('sample list characterized badge renders', async ({ page }) => {
  await page.goto('/samples')
  await expect(page.locator('tbody tr').first()).toBeVisible({ timeout: 10_000 })

  // Filter to show only characterized samples and verify the badge
  const searchInput = page.getByPlaceholder(/search by id or description/i)
  await searchInput.fill('20250212_2A')
  await expect(page.getByText('20250212_2A')).toBeVisible({ timeout: 8_000 })
  // The row should show the "Yes" characterized badge
  const row = page.locator('tbody tr').filter({ hasText: '20250212_2A' })
  await expect(row.getByText('Yes')).toBeVisible()
})

// ── Sample detail — regression tests ────────────────────────────────────────

test('characterized sample 20250212_2A detail opens without error', async ({ page }) => {
  // This is the primary regression test for the experiment_type.value AttributeError.
  // Before the fix, GET /api/samples/20250212_2A returned 500 because
  // ExperimentalConditions.experiment_type is a plain String column but the
  // router called .value on it as if it were an enum object.
  await page.goto('/samples/20250212_2A')

  // Must NOT show the error fallback
  await expect(page.getByText(/sample not found/i)).not.toBeVisible({ timeout: 10_000 })

  // Should show the sample ID heading
  await expect(page.getByRole('heading', { name: '20250212_2A' })).toBeVisible({ timeout: 10_000 })

  // Characterized indicator should be present in the overview
  await expect(page.getByText('Yes')).toBeVisible()
})

test('characterized sample 20250529_2C detail opens without error', async ({ page }) => {
  await page.goto('/samples/20250529_2C')

  await expect(page.getByText(/sample not found/i)).not.toBeVisible({ timeout: 10_000 })
  await expect(page.getByRole('heading', { name: '20250529_2C' })).toBeVisible({ timeout: 10_000 })
})

test('uncharacterized sample detail opens and shows overview fields', async ({ page }) => {
  await page.goto('/samples/20250118_1')

  await expect(page.getByText(/sample not found/i)).not.toBeVisible({ timeout: 10_000 })
  await expect(page.getByRole('heading', { name: '20250118_1' })).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('Sample Details')).toBeVisible()
})

// ── Sample detail — tab navigation ──────────────────────────────────────────

test('sample detail tabs switch correctly', async ({ page }) => {
  await page.goto('/samples/20250118_1')
  await expect(page.getByRole('heading', { name: '20250118_1' })).toBeVisible({ timeout: 10_000 })

  // Overview tab is active by default
  await expect(page.getByText('Sample Details')).toBeVisible()

  // Switch to Photos tab
  await page.getByRole('button', { name: /photos/i }).click()
  // Photos tab content: "No photos yet." text or a photo label — use first() to avoid strict-mode
  await expect(
    page.getByText(/no photos yet|upload photo/i).first()
  ).toBeVisible({ timeout: 5_000 })

  // Switch to Analyses tab
  await page.getByRole('button', { name: /analyses/i }).click()
  // Analyses tab renders the add-analysis button regardless of data
  await expect(
    page.getByRole('button', { name: /add analysis/i }).first()
  ).toBeVisible({ timeout: 5_000 })

  // Switch to Activity tab — just verify the tab button itself remains visible (content may be empty)
  await page.getByRole('button', { name: /activity/i }).click()
  await expect(page.getByRole('button', { name: /activity/i })).toBeVisible()
})

test('characterized sample tabs show analyses and linked experiments', async ({ page }) => {
  await page.goto('/samples/20250212_2A')
  await expect(page.getByRole('heading', { name: '20250212_2A' })).toBeVisible({ timeout: 10_000 })

  // Linked experiments table should be visible on the overview tab
  await expect(page.getByText('Linked Experiments')).toBeVisible({ timeout: 5_000 })
  // At least one experiment row
  await expect(page.locator('tbody tr').first()).toBeVisible()
})

// ── Sample editor ────────────────────────────────────────────────────────────

test('sample editor opens, edits description, and saves', async ({ page }) => {
  // Use 20250118_1 — uncharacterized, low risk of side effects
  await page.goto('/samples/20250118_1')
  await expect(page.getByRole('heading', { name: '20250118_1' })).toBeVisible({ timeout: 10_000 })

  // Click the Edit button
  await page.getByRole('button', { name: /^edit$/i }).click()

  // Form should now be visible with a description textarea
  const descTextarea = page.locator('textarea')
  await expect(descTextarea).toBeVisible()

  // Change the description (keep original content + tag so it's reversible)
  const originalText = await descTextarea.inputValue()
  const newText = originalText.replace(/ \[e2e\]$/, '') + ' [e2e]'
  await descTextarea.fill(newText)

  // Save
  await page.getByRole('button', { name: /^save$/i }).click()

  // Editor should close (Save button disappears) and the new description should be shown
  await expect(page.getByRole('button', { name: /^save$/i })).not.toBeVisible({ timeout: 8_000 })
  await expect(page.getByText('[e2e]')).toBeVisible()
})

test('sample editor cancel does not persist changes', async ({ page }) => {
  await page.goto('/samples/20250118_1')
  await expect(page.getByRole('heading', { name: '20250118_1' })).toBeVisible({ timeout: 10_000 })

  await page.getByRole('button', { name: /^edit$/i }).click()
  const descTextarea = page.locator('textarea')
  await descTextarea.fill('This text should not be saved')

  await page.getByRole('button', { name: /cancel/i }).click()

  // Save button gone, unsaved text gone
  await expect(page.getByRole('button', { name: /^save$/i })).not.toBeVisible()
  await expect(page.getByText('This text should not be saved')).not.toBeVisible()
})

// ── New sample modal ─────────────────────────────────────────────────────────

test('new sample modal creates sample and redirects to detail page', async ({ page }) => {
  await page.goto('/samples')
  await expect(page.getByText(/\d+ samples/)).toBeVisible({ timeout: 10_000 })

  await page.getByRole('button', { name: /\+ new sample/i }).click()

  // Modal renders with title "New Sample"
  await expect(page.getByText('New Sample').first()).toBeVisible({ timeout: 5_000 })

  const sampleId = `e2e-new-${Date.now()}`
  // The Sample ID input is labeled "Sample ID *"
  await page.getByLabel('Sample ID *').fill(sampleId)

  await page.getByRole('button', { name: /create sample/i }).click()

  // After creation the app navigates to /samples/<id>
  await expect(page).toHaveURL(new RegExp(`/samples/${sampleId}`), { timeout: 10_000 })
  await expect(page.getByRole('heading', { name: sampleId })).toBeVisible()
})

// ── Rock inventory bulk upload ───────────────────────────────────────────────

test('rock inventory upload card renders and accepts files', async ({ page }) => {
  // NOTE: The rock_inventory.py parser imports `utils.storage` and `utils.pxrf`
  // which are legacy modules that no longer exist as a standalone package. The
  // backend endpoint therefore returns 500 at runtime (locked component — cannot
  // fix without explicit user sign-off). This test validates the UI layer only:
  // the card opens, the file input is accessible, and the template download link
  // is present. The actual upload result is not asserted here.
  await page.goto('/bulk-uploads')

  // Card header should be visible in the collapsed list
  await expect(page.getByRole('button', { name: /rock inventory/i })).toBeVisible()

  // Expand the Rock Inventory card by clicking its header button
  await page.getByRole('button', { name: /rock inventory/i }).click()

  // After expanding: help text and file zone should be visible
  await expect(
    page.getByText(/required column: sample_id/i)
  ).toBeVisible({ timeout: 5_000 })

  // The template download button should be present
  const card = page.locator('.border.rounded-lg').filter({
    has: page.getByRole('button', { name: /rock inventory/i }),
  })
  await expect(card.getByRole('button', { name: /download template/i })).toBeVisible()

  // The hidden file input is accessible for programmatic upload
  const fileInput = card.locator('input[type="file"]')
  await expect(fileInput).toBeAttached()
})
