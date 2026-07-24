import { test, expect } from '../fixtures/auth'

test('master results widget shows drag-and-drop instructions, no sync button', async ({ page }) => {
  await page.goto('/bulk-uploads')
  await page.getByRole('button', { name: /Master Results Sync/i }).click()

  await expect(page.getByText(/Master_Reactor_Sampling_Tracker_v2\.xlsx/)).toBeVisible({ timeout: 5_000 })
  await expect(page.getByRole('button', { name: 'Sync from SharePoint', exact: true })).toHaveCount(0)
})

test('active widgets on top; demoted widgets collapsed into less-used section', async ({ page }) => {
  await page.goto('/bulk-uploads')

  for (const title of [
    'Master Results Sync',
    'ICP-OES Data',
    'XRD Mineralogy',
    'New Experiments',
    'Experiment Status Update',
    'ActLabs Rock Analysis',
  ]) {
    await expect(page.getByRole('button', { name: new RegExp(title, 'i') })).toBeVisible()
  }

  // Demoted rows hidden until the accordion is expanded
  await expect(page.getByRole('button', { name: /Solution Chemistry/i })).toHaveCount(0)
  await page.getByRole('button', { name: /Less-used uploads/i }).click()
  await expect(page.getByRole('button', { name: /Solution Chemistry/i })).toBeVisible()
  await expect(page.getByRole('button', { name: /pXRF Readings/i })).toBeVisible()
})
