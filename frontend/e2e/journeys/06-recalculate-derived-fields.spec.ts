/**
 * Journey 6 — Editing conditions triggers Water : Rock Ratio recalculation
 *
 * Opens the first experiment in the list, edits its conditions to set
 * rock_mass_g=10 / water_volume_mL=100 (→ ratio 10.00), then edits again to
 * set rock_mass_g=20 (→ ratio 5.00) and verifies the displayed value updates.
 */
import { test, expect } from '../fixtures/auth'

test('editing rock_mass_g triggers water_to_rock_ratio recalculation', async ({ page }) => {
  // Open the first experiment in the list
  await page.goto('/experiments')
  await page.waitForLoadState('networkidle')

  // Click the first experiment row / link in the table
  await page.getByRole('row').nth(1).click()
  await page.waitForLoadState('networkidle')

  // Conditions tab is active by default — click it explicitly to be safe
  await page.getByRole('button', { name: 'Conditions' }).click()

  // Open the Edit Conditions modal
  await page.getByRole('button', { name: 'Edit' }).click()
  await expect(page.getByText(/edit conditions/i)).toBeVisible()

  // Set known values: rock 10 g, water 100 mL → ratio must become 10.00
  await page.getByLabel(/rock mass \(g\)/i).fill('10')
  await page.getByLabel(/water volume \(mL\)/i).fill('100')
  await page.getByRole('button', { name: 'Save' }).click()

  // Modal closes; conditions tab shows updated ratio
  await expect(page.getByText('Water : Rock Ratio')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('10.00')).toBeVisible()

  // ── Second edit: change rock mass only → ratio must change to 5.00 ──────
  await page.getByRole('button', { name: 'Edit' }).click()
  await expect(page.getByText(/edit conditions/i)).toBeVisible()

  await page.getByLabel(/rock mass \(g\)/i).fill('20')
  await page.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByText('Water : Rock Ratio')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('5.00')).toBeVisible()
})
