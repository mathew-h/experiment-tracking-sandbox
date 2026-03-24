/**
 * Journey 4 — Status change via reactor grid persists
 *
 * Finds the first ONGOING experiment on the dashboard reactor grid, reads its
 * experiment ID, changes status to COMPLETED via the interactive dropdown,
 * then navigates to the experiment detail page and confirms the badge shows
 * COMPLETED.
 *
 * Note: the dashboard only renders ONGOING experiments, so the card
 * disappears after the mutation — persistence is verified on the detail page.
 */
import { test, expect } from '../fixtures/auth'

test('status change via reactor grid persists to experiment detail', async ({ page }) => {
  await page.goto('/dashboard')
  await page.waitForLoadState('networkidle')

  // Find the first interactive ONGOING status badge (title="Change status")
  const ongoingBadge = page
    .locator('button[title="Change status"]')
    .filter({ hasText: /ONGOING/i })
    .first()
  await expect(ongoingBadge).toBeVisible({ timeout: 10_000 })

  // Traverse up to the Card root (button → .relative → justify-between div → Card)
  const cardRoot = ongoingBadge.locator('../../..')
  // The experiment_id paragraph has class "text-sm font-medium … font-mono-data"
  const expId = (await cardRoot.locator('p.font-mono-data').nth(1).textContent())?.trim()
  expect(expId).toBeTruthy()

  // Open the status dropdown and select COMPLETED
  await ongoingBadge.click()
  const relativeWrapper = ongoingBadge.locator('..')
  const completedBtn = relativeWrapper.getByRole('button', { name: /^COMPLETED$/ })
  await expect(completedBtn).toBeVisible({ timeout: 3_000 })
  await completedBtn.click()

  // Wait for the mutation and React Query invalidation to settle
  await page.waitForTimeout(800)

  // Navigate to the experiment detail page and verify the status badge
  await page.goto(`/experiments/${expId}`)
  await page.waitForLoadState('networkidle')

  // The simple (display-only) StatusBadge in ExperimentDetail shows the status
  await expect(page.getByText(/COMPLETED/i).first()).toBeVisible({ timeout: 10_000 })
})
