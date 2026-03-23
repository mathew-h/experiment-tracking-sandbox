import { test, expect } from '../fixtures/auth'
import * as path from 'path'
import * as url from 'url'

const __dirname = path.dirname(url.fileURLToPath(import.meta.url))
const ICP_FILE = path.resolve(__dirname, '../../../docs/sample_data/icp_raw_data.csv')

test('ICP-OES upload processes without errors', async ({ page }) => {
  await page.goto('/bulk-uploads')

  // Open the ICP-OES Data accordion
  await page.getByRole('button', { name: /ICP-OES Data/i }).click()

  const card = page.locator('.rounded-lg').filter({
    has: page.getByRole('button', { name: /ICP-OES Data/i }),
  })
  const fileInput = card.locator('input[type="file"]')
  await fileInput.setInputFiles(ICP_FILE)

  await expect(page.getByText(/Created:/)).toBeVisible({ timeout: 15_000 })
  const errorBadge = page.getByText(/^Errors:/)
  await expect(errorBadge).not.toBeVisible()
})
