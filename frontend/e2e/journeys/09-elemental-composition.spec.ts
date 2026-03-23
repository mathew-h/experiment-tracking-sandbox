import { test, expect } from '../fixtures/auth'
import * as path from 'path'
import * as url from 'url'

const __dirname = path.dirname(url.fileURLToPath(import.meta.url))
// Wide-format fixture: sample_id column + plain analyte-symbol columns
// Sample SC-B-01 must exist in the dev DB (seeded at initial data load)
const WIDE_FILE = path.resolve(
  __dirname,
  '../../../docs/sample_data/elemental_composition_wide.xlsx'
)

test('elemental composition wide upload creates records', async ({ page }) => {
  await page.goto('/bulk-uploads')

  await page.getByRole('button', { name: /Sample Chemical Composition/i }).click()

  const card = page.locator('.rounded-lg').filter({
    has: page.getByRole('button', { name: /Sample Chemical Composition/i }),
  })
  const fileInput = card.locator('input[type="file"]')
  await fileInput.setInputFiles(WIDE_FILE)

  await expect(
    page.getByText(/Created:|Updated:|Errors:/).first()
  ).toBeVisible({ timeout: 15_000 })

  // No errors — SC-B-01 exists and analyte symbols are plain headers
  const errorBadge = page.getByText(/^Errors:/)
  await expect(errorBadge).not.toBeVisible()
})
