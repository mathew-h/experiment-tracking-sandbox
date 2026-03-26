import { useState, FormEvent } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/auth/AuthContext'
import { Button, Input } from '@/components/ui'
import { apiClient } from '@/api/client'

type Tab = 'login' | 'register'

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

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 px-3 py-2.5 rounded bg-red-500/10 border border-red-500/30 text-xs text-red-400">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0 mt-0.5">
        <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M7 4v3.5M7 9.5v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
      {message}
    </div>
  )
}

function LoginForm() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

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

      {error && <ErrorBanner message={error} />}

      <Button type="submit" variant="primary" size="md" loading={loading} className="w-full mt-1">
        {loading ? 'Signing in…' : 'Sign in'}
      </Button>
    </form>
  )
}

function RegisterForm() {
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [role, setRole] = useState('researcher')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccess(null)

    if (!email.toLowerCase().endsWith('@addisenergy.com')) {
      setError('Only @addisenergy.com email addresses are accepted.')
      return
    }

    setLoading(true)
    try {
      const res = await apiClient.post<{ message: string }>('/auth/register', {
        email,
        password,
        display_name: displayName,
        role,
      })
      setSuccess(res.data.message)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Request failed'
      if (msg.includes('already exists')) {
        setError('A request for this email already exists. Contact your lab admin.')
      } else {
        setError(msg || 'Could not submit request. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className="flex flex-col items-center gap-3 py-4 text-center">
        <svg width="32" height="32" viewBox="0 0 32 32" fill="none" className="text-status-ok">
          <circle cx="16" cy="16" r="14" stroke="currentColor" strokeWidth="2"/>
          <path d="M10 16.5l4 4 8-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <p className="text-sm font-semibold text-ink-primary">Request submitted</p>
        <p className="text-xs text-ink-muted">{success}</p>
      </div>
    )
  }

  return (
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
        label="Display name"
        type="text"
        placeholder="Your name"
        value={displayName}
        onChange={(e) => setDisplayName(e.target.value)}
        autoComplete="name"
        required
        disabled={loading}
      />
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-ink-secondary">Role</label>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          disabled={loading}
          className="w-full rounded-lg border border-surface-border bg-surface-input px-3 py-2 text-sm text-navy-900 focus:outline-none focus:ring-2 focus:ring-brand-primary/40 disabled:opacity-50"
        >
          <option value="researcher">Researcher</option>
          <option value="admin">Admin</option>
        </select>
      </div>
      <Input
        label="Password"
        type="password"
        placeholder="Min. 8 characters"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="new-password"
        required
        disabled={loading}
      />

      {error && <ErrorBanner message={error} />}

      <Button type="submit" variant="primary" size="md" loading={loading} className="w-full mt-1">
        {loading ? 'Submitting…' : 'Request access'}
      </Button>
    </form>
  )
}

/** Firebase email/password login page with domain restriction to @addisenergy.com. */
export function LoginPage() {
  const { configured } = useAuth()
  const [activeTab, setActiveTab] = useState<Tab>('login')

  if (!configured) return <FirebaseConfigWarning />

  return (
    <div className="bg-surface-overlay border border-surface-border rounded-xl p-6 shadow-panel-lg">
      {/* Tabs */}
      <div className="flex border-b border-surface-border mb-5">
        <button
          type="button"
          onClick={() => setActiveTab('login')}
          className={`pb-2.5 px-1 mr-5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'login'
              ? 'border-brand-primary text-ink-primary'
              : 'border-transparent text-ink-muted hover:text-ink-secondary'
          }`}
        >
          Sign in
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('register')}
          className={`pb-2.5 px-1 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'register'
              ? 'border-brand-primary text-ink-primary'
              : 'border-transparent text-ink-muted hover:text-ink-secondary'
          }`}
        >
          Request access
        </button>
      </div>

      {activeTab === 'login' && (
        <>
          <p className="text-xs text-ink-muted mb-4">@addisenergy.com accounts only</p>
          <LoginForm />
        </>
      )}

      {activeTab === 'register' && (
        <>
          <p className="text-xs text-ink-muted mb-4">
            Submit a request — your lab admin will approve your account.
          </p>
          <RegisterForm />
        </>
      )}
    </div>
  )
}
