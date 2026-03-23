import { test, expect } from '../fixtures/auth'
import * as path from 'path'
import * as url from 'url'

const __dirname = path.dirname(url.fileURLToPath(import.meta.url))
const SAMPLE_FILE = path.resolve(__dirname, '../../../docs/sample_data/new_experiments_template.xlsx')

test('new experiments upload processes without errors', async ({ page }) => {
  await page.goto('/bulk-uploads')

  // Open the New Experiments accordion by clicking its header
  await page.getByRole('button', { name: /New Experiments/i }).click()

  // Verify Next-ID chips are visible (including Autoclave after our fix)
  await expect(page.getByText('HPHT:')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('Autoclave:')).toBeVisible()

  // Upload the file via the hidden file input inside the New Experiments card
  const card = page.locator('.rounded-lg').filter({
    has: page.getByRole('button', { name: /New Experiments/ }),
  })
  const fileInput = card.locator('input[type="file"]')
  await fileInput.setInputFiles(SAMPLE_FILE)

  // Wait for upload result badges
  await expect(page.getByText(/Created:/)).toBeVisible({ timeout: 15_000 })

  // No errors reported
  const errorBadge = page.getByText(/^Errors:/)
  await expect(errorBadge).not.toBeVisible()
})
