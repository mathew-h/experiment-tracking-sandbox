/**
 * Journey 15 — wt% of fluid additive unit (issue #25)
 *
 * Acceptance criteria covered here:
 * - 'wt% of fluid' appears in the unit dropdown in the ConditionsTab additive form
 * - 'wt% of fluid' appears in the unit dropdown in New Experiment Step 3 (Additives)
 *
 * These tests check for the PRESENCE of the dropdown option only.
 * End-to-end persistence requires a running API server and is covered by backend tests.
 */
import { test, expect } from '../fixtures/auth'

test.describe('wt% of fluid additive unit (issue #25)', () => {
  test('wt% of fluid appears in ADDITIVE_UNIT_OPTIONS dropdown in ConditionsTab', async ({ page }) => {
    // Navigate to the experiments list and open the first experiment
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    // Click into the first experiment link visible on the page
    const firstExperimentLink = page.getByRole('link', { name: /experiment/i }).first()
    await firstExperimentLink.click()
    await page.waitForLoadState('networkidle')

    // Open the Conditions tab
    await page.getByRole('tab', { name: /conditions/i }).click()
    await page.waitForLoadState('networkidle')

    // Click Add Additive button (or Edit button on an existing additive)
    const addAdditiveButton = page.getByRole('button', { name: /add additive/i })
    if (await addAdditiveButton.isVisible()) {
      await addAdditiveButton.click()
    } else {
      // Fall back: click the edit (pencil) button on the first existing additive
      await page.locator('button[aria-label*="edit"], button[title*="edit"]').first().click()
    }

    // Find the Unit select element and check its options
    // Get all option values from any select on the page (the unit select is rendered near "Unit" label)
    const unitOptions = await page.locator('select option').allTextContents()
    expect(unitOptions).toContain('wt% of fluid')
  })

  test('wt% of fluid appears in AMOUNT_UNITS in New Experiment Step 3', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    // Click New Experiment button
    await page.getByRole('button', { name: /new experiment/i }).click()
    await page.waitForLoadState('networkidle')

    // Step 1: fill experiment ID minimally and proceed
    const expIdInput = page.getByLabel(/experiment id/i).or(page.getByPlaceholder(/experiment id/i))
    if (await expIdInput.isVisible()) {
      await expIdInput.fill('TEST-E2E-25')
    }

    // Click Next / Continue until we reach the additives step (step 3)
    const nextButton = page.getByRole('button', { name: /next|continue/i }).first()
    if (await nextButton.isVisible()) {
      await nextButton.click()
      await page.waitForTimeout(500)
      const nextButton2 = page.getByRole('button', { name: /next|continue/i }).first()
      if (await nextButton2.isVisible()) {
        await nextButton2.click()
        await page.waitForTimeout(500)
      }
    }

    // On the additives step, add an additive to trigger the unit dropdown
    const addButton = page.getByRole('button', { name: /add additive|add chemical/i }).first()
    if (await addButton.isVisible()) {
      await addButton.click()
    }

    // Check that unit select contains wt% of fluid
    const unitOptions = await page.locator('select option').allTextContents()
    expect(unitOptions).toContain('wt% of fluid')
  })
})
