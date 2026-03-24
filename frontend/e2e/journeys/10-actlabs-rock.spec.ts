import { test, expect } from '../fixtures/auth'
import * as path from 'path'
import * as url from 'url'

const __dirname = path.dirname(url.fileURLToPath(import.meta.url))
// Native ActLabs report: positional layout, no normal header row, duplicate symbol columns
// Reference standards TAMARACK, MONAZITE SAND, PNNL CORE must exist in SampleInfo
const ACTLABS_FILE = path.resolve(
  __dirname,
  '../../../docs/sample_data/sample_actlabs_rock_composition.xlsx'
)

test('ActLabs Rock Analysis upload creates elemental records', async ({ page }) => {
  await page.goto('/bulk-uploads')

  await page.getByRole('button', { name: /ActLabs Rock Analysis/i }).click()

  const card = page.locator('.rounded-lg').filter({
    has: page.getByRole('button', { name: /ActLabs Rock Analysis/i }),
  })
  const fileInput = card.locator('input[type="file"]')
  await fileInput.setInputFiles(ACTLABS_FILE)

  await expect(
    page.getByText(/Created:|Updated:|Errors:/).first()
  ).toBeVisible({ timeout: 15_000 })

  // At least one record created or updated (TAMARACK / MONAZITE SAND / PNNL CORE all seeded)
  await expect(page.getByText(/Created: [1-9]|Updated: [1-9]/i)).toBeVisible()

  const errorBadge = page.getByText(/^Errors:/)
  await expect(errorBadge).not.toBeVisible()
})
