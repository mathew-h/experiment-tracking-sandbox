import { test, expect } from '../fixtures/auth'

test('dashboard loads after auth', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Reactor Status', { exact: true })).toBeVisible()
})

test('sidebar navigation links are present', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('link', { name: /experiments/i })).toBeVisible()
  await expect(page.getByRole('link', { name: /bulk uploads/i })).toBeVisible()
})
