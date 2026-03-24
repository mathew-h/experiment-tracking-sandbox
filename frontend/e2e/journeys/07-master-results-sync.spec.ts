// PRECONDITION: master_results_path must be configured in app_config table.
// One-time setup via Swagger UI:
//   1. Open http://localhost:8000/docs
//   2. PATCH /api/bulk-uploads/master-results/config
//   3. Set path to the absolute path of the sample file, e.g.:
//      "C:\\Users\\MathewHearl\\Documents\\0x_Software\\database_sandbox\\experiment_tracking_sandbox\\docs\\sample_data\\Master Reactor Sampling Tracker.xlsx"
//   4. Verify GET /api/bulk-uploads/master-results/config returns the path.
import { test, expect } from '../fixtures/auth'

test('master results sync button triggers sync', async ({ page }) => {
  await page.goto('/bulk-uploads')
  await page.getByText('Master Results Sync').click()

  const syncBtn = page.getByRole('button', { name: 'Sync from SharePoint', exact: true })
  await expect(syncBtn).toBeVisible({ timeout: 5_000 })

  await syncBtn.click()

  // Wait for result — any badge with count indicates sync ran
  await expect(page.getByText(/Created:|Updated:|Skipped:/i).first()).toBeVisible({ timeout: 20_000 })
})
