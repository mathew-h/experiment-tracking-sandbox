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

  // The Sync Now button is only visible when a path is configured.
  // If the settings panel is shown instead, complete the precondition setup first.
  const syncBtn = page.getByRole('button', { name: /sync now/i })
  await expect(syncBtn).toBeVisible({ timeout: 5_000 })

  await syncBtn.click()

  // Wait for result — any of created / updated / skipped indicates sync ran
  await expect(page.getByText(/created|updated|skipped/i)).toBeVisible({ timeout: 20_000 })
})
