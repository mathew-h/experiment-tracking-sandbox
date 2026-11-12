import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const h = vi.hoisted(() => ({
  post: vi.fn(),
  signIn: vi.fn(),
  authError: null as string | null,
  user: null as unknown,
}))

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    configured: true,
    signIn: h.signIn,
    authError: h.authError,
    user: h.user,
  }),
}))
vi.mock('@/api/client', () => ({ apiClient: { post: h.post } }))

import { Routes, Route } from 'react-router-dom'
import { LoginPage } from '../Login'

function renderLoginFrom(target: string) {
  return render(
    <MemoryRouter
      initialEntries={[{ pathname: '/login', state: { from: { pathname: target } } }]}
    >
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path={target} element={<p>TARGET PAGE</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    h.post.mockReset()
    h.signIn.mockReset()
    h.authError = null
    h.user = null
  })

  it('does not navigate when signIn resolves before the user is approved/set', async () => {
    h.signIn.mockResolvedValue(undefined)
    const { container } = renderLoginFrom('/target')
    fireEvent.change(screen.getByPlaceholderText('you@addisenergy.com'), {
      target: { value: 'a@addisenergy.com' },
    })
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'pw' } })
    fireEvent.submit(container.querySelector('form') as HTMLFormElement)
    await waitFor(() => expect(h.signIn).toHaveBeenCalledTimes(1))
    // Submit button text returns from "Signing in…" to "Sign in" (tab + submit = 2)
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Sign in' })).toHaveLength(2))
    expect(screen.queryByText('TARGET PAGE')).toBeNull()
  })

  it('redirects to the original page once the user is set', () => {
    h.user = { uid: 'u1' }
    renderLoginFrom('/target')
    expect(screen.getByText('TARGET PAGE')).toBeTruthy()
  })

  it('register form has no password field', () => {
    const { container } = renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Request access' }))
    expect(container.querySelector('[autocomplete="new-password"]')).toBeNull()
    expect(container.querySelector('input[type="password"]')).toBeNull()
  })

  it('register request body has no password', async () => {
    h.post.mockResolvedValue({ data: { message: 'ok' } })
    const { container } = renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Request access' }))
    fireEvent.change(screen.getByPlaceholderText('you@addisenergy.com'), {
      target: { value: 'new@addisenergy.com' },
    })
    fireEvent.change(screen.getByPlaceholderText('Your name'), { target: { value: 'New' } })
    fireEvent.submit(container.querySelector('form') as HTMLFormElement)

    await waitFor(() => expect(h.post).toHaveBeenCalledTimes(1))
    const [url, body] = h.post.mock.calls[0]
    expect(url).toBe('/auth/register')
    expect(Object.keys(body).sort()).toEqual(['display_name', 'email', 'role'])
  })

  it('login form shows authError from context', () => {
    h.authError = 'Your account has not been approved yet. Contact your lab admin.'
    renderPage()
    expect(
      screen.getByText('Your account has not been approved yet. Contact your lab admin.'),
    ).toBeTruthy()
  })
})
