/**
 * Journey 1 — Create experiment end-to-end
 *
 * Walks through the 4-step NewExperiment form (Basic Info → Conditions →
 * Additives → Review), submits, then verifies the derived Water : Rock Ratio
 * field is visible on the Conditions tab of the new experiment.
 */
import { test, expect } from '../fixtures/auth'

test('create experiment with conditions and verify derived fields', async ({ page }) => {
  await page.goto('/experiments/new')

  // ── Step 1: Basic Info ──────────────────────────────────────────────────
  // Select experiment type first — this triggers the next-ID fetch
  await page.getByLabel(/experiment type/i).selectOption('HPHT')

  // Wait for the auto-assigned Experiment ID to stop showing "Loading…"
  const idInput = page.getByLabel(/experiment id/i)
  await expect(idInput).not.toHaveValue(/loading/i, { timeout: 10_000 })
  await expect(idInput).not.toHaveValue('', { timeout: 10_000 })

  // Capture the assigned ID so we can find the experiment after creation
  const expId = await idInput.inputValue()
  expect(expId).toBeTruthy()

  await page.getByRole('button', { name: /next.*condition/i }).click()

  // ── Step 2: Conditions ──────────────────────────────────────────────────
  await page.getByLabel(/rock mass/i).fill('10')
  await page.getByLabel(/water volume/i).fill('100')
  await page.getByRole('button', { name: /next.*additive/i }).click()

  // ── Step 3: Additives — skip ────────────────────────────────────────────
  await page.getByRole('button', { name: /next.*review/i }).click()

  // ── Step 4: Review ─────────────────────────────────────────────────────
  await expect(page.getByText(expId)).toBeVisible()
  await page.getByRole('button', { name: /create experiment/i }).click()

  // After creation the app navigates away — wait for that
  await expect(page).not.toHaveURL(/\/experiments\/new/, { timeout: 15_000 })

  // Navigate to experiments list and open the newly-created experiment
  await page.goto('/experiments')
  await page.getByText(expId).first().click()

  // Conditions tab should be active by default; Water : Rock Ratio must show
  await expect(page.getByText('Water : Rock Ratio')).toBeVisible({ timeout: 10_000 })
})
