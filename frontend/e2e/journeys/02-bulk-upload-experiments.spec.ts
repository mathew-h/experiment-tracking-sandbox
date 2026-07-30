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

  // Preview-first: the drop opens a review modal and writes nothing yet (issue #100)
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Review upload plan')).toBeVisible({ timeout: 15_000 })
  await expect(dialog.getByText(/Nothing has been written yet/i)).toBeVisible()

  // No conflicts in the sample template, so commit is available
  const commit = dialog.getByRole('button', { name: /^Commit \d+ change/ })
  await expect(commit).toBeEnabled()
  await commit.click()

  // Committed — the modal reports the real counts
  await expect(dialog.getByText('Upload complete')).toBeVisible({ timeout: 15_000 })
  await expect(dialog.getByText(/Created: \d+/)).toBeVisible()
})
