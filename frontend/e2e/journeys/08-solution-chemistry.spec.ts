import { test, expect } from '../fixtures/auth'
import * as path from 'path'
import * as url from 'url'

const __dirname = path.dirname(url.fileURLToPath(import.meta.url))
const SOL_CHEM_FILE = path.resolve(
  __dirname,
  '../../../docs/sample_data/solution chemistry upload.xlsx'
)

test('solution chemistry upload processes without errors', async ({ page }) => {
  await page.goto('/bulk-uploads')

  // Open the Solution Chemistry accordion
  await page.getByRole('button', { name: /Solution Chemistry/i }).click()

  const card = page.locator('.rounded-lg').filter({
    has: page.getByRole('button', { name: /Solution Chemistry/i }),
  })
  const fileInput = card.locator('input[type="file"]')
  await fileInput.setInputFiles(SOL_CHEM_FILE)

  // Wait for any result (created/updated/errors badge) to appear
  await expect(
    page.getByText(/Created:|Errors:|Updated:/).first()
  ).toBeVisible({ timeout: 30_000 })

  const errorBadge = page.getByText(/^Errors:/)
  await expect(errorBadge).not.toBeVisible()
})
