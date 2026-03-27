/**
 * Playwright auth fixtures.
 *
 * Firebase Web SDK v9 stores auth state in IndexedDB, which Playwright's
 * storageState does not capture. The solution: a worker-scoped BrowserContext
 * that logs in once and is reused across all tests in the worker.
 *
 * Each test receives its own Page (for isolation), but shares the authenticated
 * BrowserContext so Firebase auth in IndexedDB persists throughout the run.
 */
import { test as base, BrowserContext, Page } from '@playwright/test'
import * as dotenv from 'dotenv'
import * as path from 'path'
import * as url from 'url'

const __dirname = path.dirname(url.fileURLToPath(import.meta.url))
dotenv.config({ path: path.join(__dirname, '../.env.e2e') })

type AuthWorkerFixtures = {
  authedContext: BrowserContext
}

type AuthTestFixtures = {
  page: Page
}

export const test = base.extend<AuthTestFixtures, AuthWorkerFixtures>({
  // One authenticated browser context per worker (= once for the whole run with workers:1)
  authedContext: [
    async ({ browser }, use) => {
      const context = await browser.newContext()
      const loginPage = await context.newPage()

      await loginPage.goto('http://localhost:5173/login')
      await loginPage.getByPlaceholder('you@addisenergy.com').fill(process.env.E2E_EMAIL!)
      await loginPage.getByPlaceholder('••••••••').fill(process.env.E2E_PASSWORD!)
      // Use type="submit" to avoid matching the "Sign in" tab button added with the Register tab
      await loginPage.locator('button[type="submit"]').click()

      // Wait for redirect away from login page (dashboard is at /)
      await loginPage.waitForFunction(
        () => !window.location.pathname.includes('/login'),
        { timeout: 15_000 }
      )
      await loginPage.close()

      await use(context)
      await context.close()
    },
    { scope: 'worker' },
  ],

  // Each test gets its own page within the shared authenticated context
  page: async ({ authedContext }, use) => {
    const page = await authedContext.newPage()
    await use(page)
    await page.close()
  },
})

export { expect } from '@playwright/test'
