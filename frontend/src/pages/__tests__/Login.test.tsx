import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const h = vi.hoisted(() => ({
  post: vi.fn(),
  authError: null as string | null,
}))

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ configured: true, signIn: vi.fn(), authError: h.authError }),
}))
vi.mock('@/api/client', () => ({ apiClient: { post: h.post } }))

import { LoginPage } from '../Login'

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
    h.authError = null
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
