import { useState, FormEvent } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/auth/AuthContext'
import { Button, Input } from '@/components/ui'

function FirebaseConfigWarning() {
  return (
    <div className="bg-surface-overlay border border-status-warning/30 rounded-xl p-5 text-center space-y-2">
      <p className="text-sm font-semibold text-status-warning">Firebase not configured</p>
      <p className="text-xs text-ink-muted">
        Create <code className="font-mono-data bg-surface-raised px-1 py-0.5 rounded text-ink-secondary">frontend/.env.local</code> from{' '}
        <code className="font-mono-data bg-surface-raised px-1 py-0.5 rounded text-ink-secondary">.env.example</code> and add your Firebase credentials.
      </p>
      <p className="text-xs text-ink-muted">Restart the dev server after saving.</p>
    </div>
  )
}

/** Firebase email/password login page with domain restriction to @addisenergy.com. */
export function LoginPage() {
  const { signIn, configured } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  if (!configured) return <FirebaseConfigWarning />

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await signIn(email, password)
      navigate(from, { replace: true })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Sign in failed'
      if (msg.includes('user-not-found') || msg.includes('wrong-password') || msg.includes('invalid-credential')) {
        setError('Invalid email or password.')
      } else if (msg.includes('too-many-requests')) {
        setError('Too many attempts. Please try again later.')
      } else if (msg.includes('network')) {
        setError('Network error. Check your connection.')
      } else {
        setError('Sign in failed. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-surface-overlay border border-surface-border rounded-xl p-6 shadow-panel-lg">
      <div className="mb-5">
        <h2 className="text-base font-semibold text-ink-primary">Sign in</h2>
        <p className="text-xs text-ink-muted mt-0.5">@addisenergy.com accounts only</p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Input
          label="Email"
          type="email"
          placeholder="you@addisenergy.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
          disabled={loading}
        />
        <Input
          label="Password"
          type="password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
          disabled={loading}
        />

        {error && (
          <div className="flex items-start gap-2 px-3 py-2.5 rounded bg-red-500/10 border border-red-500/30 text-xs text-red-400">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0 mt-0.5">
              <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M7 4v3.5M7 9.5v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            {error}
          </div>
        )}

        <Button type="submit" variant="primary" size="md" loading={loading} className="w-full mt-1">
          {loading ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>

      <p className="text-xs text-ink-muted text-center mt-5">
        Need access? Contact your lab administrator.
      </p>
    </div>
  )
}
