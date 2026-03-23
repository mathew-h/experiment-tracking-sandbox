import { test, expect } from '../fixtures/auth'
import * as path from 'path'
import * as url from 'url'

const __dirname = path.dirname(url.fileURLToPath(import.meta.url))
const XRD_FILE = path.resolve(
  __dirname,
  '../../../docs/sample_data/XRD_result_070d19.xlsx'
)

test('XRD Aeris upload creates mineral phase records', async ({ page }) => {
  await page.goto('/bulk-uploads')

  // Open the XRD Mineralogy accordion
  await page.getByRole('button', { name: /XRD Mineralogy/i }).click()

  const card = page.locator('.rounded-lg').filter({
    has: page.getByRole('button', { name: /XRD Mineralogy/i }),
  })
  const fileInput = card.locator('input[type="file"]')
  await fileInput.setInputFiles(XRD_FILE)

  // Wait for upload result badges
  await expect(
    page.getByText(/Created:|Updated:|Errors:/).first()
  ).toBeVisible({ timeout: 15_000 })

  // Verify at least one mineral phase row was created or updated
  await expect(
    page.getByText(/Created: [1-9]|Updated: [1-9]/i)
  ).toBeVisible()

  // No errors
  const errorBadge = page.getByText(/^Errors:/)
  await expect(errorBadge).not.toBeVisible()
})
