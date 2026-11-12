import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'

type AuthCallback = (user: unknown) => Promise<void> | void

const h = vi.hoisted(() => ({
  callback: null as AuthCallback | null,
  signOut: vi.fn(),
  headers: {} as Record<string, string>,
}))

vi.mock('firebase/auth', () => ({
  onAuthStateChanged: (_auth: unknown, cb: AuthCallback) => {
    h.callback = cb
    return () => {}
  },
  signInWithEmailAndPassword: vi.fn(),
  signOut: h.signOut,
}))
vi.mock('../firebaseConfig', () => ({ auth: {}, firebaseConfigured: true }))
vi.mock('@/api/client', () => ({
  apiClient: { defaults: { headers: { common: h.headers } } },
}))

import { AuthProvider, useAuth } from '../AuthContext'

function Probe() {
  const { user, authError } = useAuth()
  return (
    <div>
      <span data-testid="user">{user ? 'signed-in' : 'signed-out'}</span>
      <span data-testid="error">{authError ?? ''}</span>
    </div>
  )
}

function fakeUser(claims: Record<string, unknown>) {
  return {
    getIdToken: vi.fn().mockResolvedValue('tok'),
    getIdTokenResult: vi.fn().mockResolvedValue({ token: 'fresh-tok', claims }),
  }
}

async function emit(user: unknown) {
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  )
  await act(async () => {
    await h.callback?.(user)
  })
}

describe('AuthProvider approved-claim gate', () => {
  beforeEach(() => {
    h.signOut.mockReset()
    for (const k of Object.keys(h.headers)) delete h.headers[k]
  })

  it('forces a token refresh when reading claims', async () => {
    const user = fakeUser({ approved: true })
    await emit(user)
    expect(user.getIdTokenResult).toHaveBeenCalledWith(true)
  })

  it('signs out and sets authError when approved claim missing', async () => {
    await emit(fakeUser({}))
    expect(h.signOut).toHaveBeenCalledTimes(1)
    await waitFor(() =>
      expect(screen.getByTestId('error').textContent).toBe(
        'Your account has not been approved yet. Contact your lab admin.',
      ),
    )
    expect(screen.getByTestId('user').textContent).toBe('signed-out')
    expect(h.headers['Authorization']).toBeUndefined()
  })

  it('sets Authorization header when approved', async () => {
    await emit(fakeUser({ approved: true }))
    await waitFor(() => expect(screen.getByTestId('user').textContent).toBe('signed-in'))
    expect(h.headers['Authorization']).toBe('Bearer fresh-tok')
    expect(h.signOut).not.toHaveBeenCalled()
  })
})
