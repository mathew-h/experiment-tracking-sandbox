import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { NotFoundPage } from '../NotFound'

function Probe() {
  return <p data-testid="path">{useLocation().pathname}</p>
}

/** The tail of App.tsx's protected routes (issue #159): an explicit /dashboard
 *  redirect, then a catch-all that names the miss instead of redirecting. */
function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route index element={<p>dashboard page</p>} />
        <Route path="/dashboard" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <Probe />
    </MemoryRouter>,
  )
}

describe('NotFoundPage (issue #159)', () => {
  it('names the attempted path and links to the four starting pages', () => {
    renderAt('/no-such-page?x=1')
    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toHaveTextContent(/^Not found$/)
    expect(screen.getByText('/no-such-page?x=1')).toHaveClass('font-mono-data')
    const hrefs = ['Dashboard', 'Experiments', 'HPHT', 'Core Floods'].map((name) =>
      screen.getByRole('link', { name }).getAttribute('href'),
    )
    expect(hrefs).toEqual(['/', '/experiments', '/hpht', '/core-floods'])
    expect(screen.getByTestId('path')).toHaveTextContent('/no-such-page')
  })

  it('keeps /dashboard working through its explicit redirect', () => {
    renderAt('/dashboard')
    expect(screen.getByText('dashboard page')).toBeInTheDocument()
    expect(screen.getByTestId('path')).toHaveTextContent(/^\/$/)
  })
})
