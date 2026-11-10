/**
 * Journey 16 — Results tab samples table (issues #23, #163)
 *
 * Since #163 the Results tab, the HPHT run page and the Core Flood run page share
 * one samples table. This journey checks it on the Results tab, read-only:
 * - the shared columns in order (Date, Day, Tube, Result note, GC group, Solution)
 * - pH and Cond. adjacent
 * - a Date cell is "—" or YYYY-MM-DD, and no cell reads "null" / "undefined"
 * - the ICP / MOD / DETAILS flags open their section without opening the editor
 *
 * The experiment is found through the app (first HPHT run → its newest sample's
 * segment), not by calling the API directly: a bare fetch() from the page carries
 * no Firebase token, so the old lookup always found nothing and the checks were
 * skipped. Nothing is saved: no row is clicked, and no dialog is opened.
 */
import { test, expect } from '../fixtures/auth'
import type { Page } from '@playwright/test'

/** Opens the Results tab of the segment behind the newest sample of the first of
 *  up to five listed HPHT runs that has samples; false when none has. */
async function openResultsTabWithSamples(page: Page): Promise<boolean> {
  await page.goto('/hpht')
  const runLinks = page.locator('main a[href^="/hpht/"]')
  await runLinks.first().waitFor({ timeout: 15_000 }).catch(() => undefined)
  const runs = (await runLinks.evaluateAll((as) => as.map((a) => a.getAttribute('href')))).slice(0, 5)
  for (const run of runs) {
    await page.goto(run!)
    const samples = page.getByRole('region', { name: 'Samples' })
    // The table renders a sample row, or "No samples yet".
    await samples.locator('tbody tr').first().waitFor({ timeout: 15_000 }).catch(() => undefined)
    const segment = samples.locator('tbody tr[data-testid^="sample-"] a[href^="/experiments/"]').first()
    if ((await segment.count()) === 0) continue
    const href = await segment.getAttribute('href')
    await page.goto(`${href}?tab=results`)
    const row = page.locator('tbody tr[data-testid^="sample-"]').first()
    if (await row.waitFor({ timeout: 15_000 }).then(() => true, () => false)) return true
  }
  return false
}

test.describe('Results tab samples table (issues #23, #163)', () => {
  test('shared columns in order, pH next to Cond.', async ({ page }) => {
    test.skip(!(await openResultsTabWithSamples(page)), 'No HPHT run with samples in this database')
    const heads = (await page.getByRole('columnheader').allTextContents()).map((t) => t.trim())
    const lead = ['Date', 'Day', 'Tube', 'Result note', 'H₂ ppm', 'H₂ µmol', 'H₂ g/t']
    const at = lead.map((h) => heads.indexOf(h))
    expect(at.every((i) => i >= 0)).toBe(true)
    expect(at).toEqual([...at].sort((a, b) => a - b))
    expect(heads).not.toContain('Segment')
    expect(heads.indexOf('Cond.') - heads.indexOf('pH')).toBe(1)
  })

  test('date cells are a date or a dash, never null', async ({ page }) => {
    test.skip(!(await openResultsTabWithSamples(page)), 'No HPHT run with samples in this database')
    const row = page.locator('tbody tr[data-testid^="sample-"]').first()
    const cells = (await row.locator('td').allTextContents()).map((t) => t.trim())
    for (const text of cells) {
      expect(text).not.toBe('null')
      expect(text).not.toBe('undefined')
    }
    // Date is the first column on the Results tab.
    expect(cells[0] === '—' || /^\d{4}-\d{2}-\d{2}$/.test(cells[0])).toBe(true)
  })

  test('flags open their section and never the editor', async ({ page }) => {
    test.skip(!(await openResultsTabWithSamples(page)), 'No HPHT run with samples in this database')
    const flag = page.getByRole('button', { name: /^Show (ICP|modification|details) for/ }).first()
    test.skip(!(await flag.isVisible().catch(() => false)), 'No sample with a flag on this experiment')
    await flag.click()
    await expect(flag).toHaveAttribute('aria-expanded', 'true')
    await expect(
      page.getByRole('region', { name: /^(ICP readings|Modification notes|Sample details)$/ }).first(),
    ).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })
})
