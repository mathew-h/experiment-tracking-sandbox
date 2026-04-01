/**
 * Journey 14 — Dashboard CF01/CF02 slot mapping (issue #26)
 *
 * Acceptance criteria covered here:
 * - CF01 slot shows an active Core Flood experiment when reactor_number = 1
 * - HPHT experiment in reactor 1 appears in R01, not CF01
 *
 * CF02 (reactor_number=2) is covered by backend tests only:
 * see tests/api/test_dashboard.py::test_core_flood_experiment_in_reactor_2_gets_cf02_label
 *
 * Approach:
 * - Create experiments via the UI (New Experiment wizard)
 * - Navigate to /dashboard and assert reactor grid slot contents
 * - Cancel created experiments in afterEach to avoid polluting other journeys
 */
import { test, expect } from '../fixtures/auth'
import type { Page } from '@playwright/test'

// Capture created experiment IDs so we can cancel them in afterEach
const createdIds: string[] = []

test.afterEach(async ({ page }) => {
  for (const expId of createdIds.splice(0)) {
    await page.goto(`/experiments/${expId}`)
    await page.waitForLoadState('networkidle')
    // Click the status badge to change to CANCELLED
    const badge = page.locator('button[title="Change status"]').first()
    if (await badge.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await badge.click()
      const cancelBtn = page.getByRole('button', { name: /^CANCELLED$/i })
      await cancelBtn.click()
      await page.waitForLoadState('networkidle')
    }
  }
})

/**
 * Helper: create a new experiment via the wizard and return its assigned ID.
 * Fills only the fields needed to reach the dashboard reactor grid.
 */
async function createExperiment(
  page: Page,
  opts: { type: string; reactorNumber: string }
): Promise<string> {
  await page.goto('/experiments/new')

  // Step 1: Basic Info — select experiment type
  await page.getByLabel(/experiment type/i).selectOption(opts.type)

  // Wait for the auto-assigned experiment ID
  const idInput = page.getByLabel(/experiment id/i)
  await expect(idInput).not.toHaveValue(/loading/i, { timeout: 10_000 })
  await expect(idInput).not.toHaveValue('', { timeout: 5_000 })
  const expId = await idInput.inputValue()
  expect(expId).toBeTruthy()

  await page.getByRole('button', { name: /next.*condition/i }).click()

  // Step 2: Conditions — set reactor number
  await page.getByLabel(/reactor number/i).fill(opts.reactorNumber)
  await page.getByRole('button', { name: /next.*additive/i }).click()

  // Step 3: Additives — skip
  await page.getByRole('button', { name: /next.*review/i }).click()

  // Step 4: Review — submit
  await page.getByRole('button', { name: /create experiment/i }).click()
  await expect(page).not.toHaveURL(/\/experiments\/new/, { timeout: 15_000 })

  return expId
}

test('CF01 slot is populated when Core Flood experiment with reactor_number=1 is ONGOING', async ({ page }) => {
  const expId = await createExperiment(page, { type: 'Core Flood', reactorNumber: '1' })
  createdIds.push(expId)

  await page.goto('/dashboard')
  await page.waitForLoadState('networkidle')

  // Find the CF01 label inside the Core Flood grid section
  const cfSection = page.locator('text=Core Flood (CF01–CF02)').locator('../..')
  await expect(cfSection).toBeVisible({ timeout: 10_000 })

  // CF01 card — the label "CF01" appears as a mono-data heading inside the section
  const cf01Label = cfSection.locator('p.font-mono-data').filter({ hasText: /^CF01$/ })
  await expect(cf01Label).toBeVisible({ timeout: 10_000 })

  // The experiment ID should appear in the same card
  // DOM: p (label) → div (label wrapper) → div (flex justify-between) → div (Card root)
  const cf01Card = cf01Label.locator('../../..')
  await expect(cf01Card.locator(`text=${expId}`)).toBeVisible({ timeout: 5_000 })

  // The status badge should say ONGOING (not "Empty")
  await expect(cf01Card.locator('text=ONGOING')).toBeVisible()
})

test('HPHT experiment in reactor_number=1 appears in R01, not CF01', async ({ page }) => {
  const expId = await createExperiment(page, { type: 'HPHT', reactorNumber: '1' })
  createdIds.push(expId)

  await page.goto('/dashboard')
  await page.waitForLoadState('networkidle')

  // R01 card should contain the experiment
  const rSection = page.locator('text=Standard Reactors (R01–R16)').locator('../..')
  await expect(rSection).toBeVisible({ timeout: 10_000 })

  const r01Label = rSection.locator('p.font-mono-data').filter({ hasText: /^R01$/ })
  await expect(r01Label).toBeVisible({ timeout: 10_000 })
  // DOM: p (label) → div (label wrapper) → div (flex justify-between) → div (Card root)
  const r01Card = r01Label.locator('../../..')
  await expect(r01Card.locator(`text=${expId}`)).toBeVisible({ timeout: 5_000 })

  // CF01 must NOT contain this experiment
  const cfSection = page.locator('text=Core Flood (CF01–CF02)').locator('../..')
  const cf01Label = cfSection.locator('p.font-mono-data').filter({ hasText: /^CF01$/ })
  await expect(cf01Label).toBeVisible({ timeout: 5_000 })
  // DOM: p (label) → div (label wrapper) → div (flex justify-between) → div (Card root)
  const cf01Card = cf01Label.locator('../../..')
  await expect(cf01Card.locator(`text=${expId}`)).not.toBeVisible()
})
