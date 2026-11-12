import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import {
  User,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut as firebaseSignOut,
} from 'firebase/auth'
import { auth, firebaseConfigured } from './firebaseConfig'
import { apiClient } from '@/api/client'

interface AuthContextValue {
  user: User | null
  token: string | null
  loading: boolean
  configured: boolean
  /** Set when a signed-in account was rejected (e.g. not yet approved); shown on the login page. */
  authError: string | null
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

const NOT_APPROVED_MESSAGE = 'Your account has not been approved yet. Contact your lab admin.'
const VERIFY_FAILED_MESSAGE = "Couldn't verify your account — check your connection and reload."

const AuthContext = createContext<AuthContextValue | null>(null)

/** Firebase auth context provider — manages ID token, user state, and login/logout. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(firebaseConfigured) // false immediately if unconfigured
  const [authError, setAuthError] = useState<string | null>(null)

  useEffect(() => {
    if (!firebaseConfigured) return
    const clearSession = () => {
      setUser(null)
      setToken(null)
      delete apiClient.defaults.headers.common['Authorization']
    }
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      try {
        if (!firebaseUser) {
          clearSession()
          return
        }
        // Force-refresh so claims set after the cached token was minted (e.g. approval) are seen.
        const result = await firebaseUser.getIdTokenResult(true)
        if (result.claims.approved === true) {
          setUser(firebaseUser)
          setToken(result.token)
          apiClient.defaults.headers.common['Authorization'] = `Bearer ${result.token}`
        } else {
          // Backend would 403 every call; sign out instead of showing a broken app.
          setAuthError(NOT_APPROVED_MESSAGE)
          clearSession()
          await firebaseSignOut(auth)
        }
      } catch {
        // Transient failure (network, quota): don't sign out, but never leave the app spinning.
        setAuthError(VERIFY_FAILED_MESSAGE)
        clearSession()
      } finally {
        setLoading(false)
      }
    })
    return unsubscribe
  }, [])

  // Proactive token refresh every 55 minutes (tokens expire at 60m)
  useEffect(() => {
    if (!user) return
    const interval = setInterval(async () => {
      const freshToken = await user.getIdToken(true)
      setToken(freshToken)
      apiClient.defaults.headers.common['Authorization'] = `Bearer ${freshToken}`
    }, 55 * 60 * 1000)
    return () => clearInterval(interval)
  }, [user])

  const signIn = async (email: string, password: string) => {
    setAuthError(null)
    await signInWithEmailAndPassword(auth, email, password)
  }

  const signOut = async () => {
    await firebaseSignOut(auth)
  }

  return (
    <AuthContext.Provider
      value={{ user, token, loading, configured: firebaseConfigured, authError, signIn, signOut }}
    >
      {children}
    </AuthContext.Provider>
  )
}

/** Hook returning the current Firebase auth state and login/logout helpers. */
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
