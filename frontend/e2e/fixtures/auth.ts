import { chromium, FullConfig } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'
import * as dotenv from 'dotenv'

dotenv.config({ path: path.join(__dirname, '../.env.e2e') })

const AUTH_FILE = path.join(__dirname, '../.auth/state.json')

export default async function globalSetup(_config: FullConfig) {
  // Ensure .auth directory exists
  fs.mkdirSync(path.dirname(AUTH_FILE), { recursive: true })

  const browser = await chromium.launch()
  const page = await browser.newPage()

  await page.goto('http://localhost:5173')

  // Fill login form (selectors from frontend/src/pages/Login.tsx)
  await page.getByPlaceholder('you@addisenergy.com').fill(process.env.E2E_EMAIL!)
  await page.getByPlaceholder('••••••••').fill(process.env.E2E_PASSWORD!)
  await page.getByRole('button', { name: /sign in/i }).click()

  // Wait for redirect to dashboard
  await page.waitForURL('**/dashboard', { timeout: 15_000 })

  // Save auth state
  await page.context().storageState({ path: AUTH_FILE })
  await browser.close()

  console.log('✓ Auth state saved to', AUTH_FILE)
}
