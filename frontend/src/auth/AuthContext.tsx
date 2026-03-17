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
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(firebaseConfigured) // false immediately if unconfigured

  useEffect(() => {
    if (!firebaseConfigured) return
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      if (firebaseUser) {
        const idToken = await firebaseUser.getIdToken()
        setUser(firebaseUser)
        setToken(idToken)
        apiClient.defaults.headers.common['Authorization'] = `Bearer ${idToken}`
      } else {
        setUser(null)
        setToken(null)
        delete apiClient.defaults.headers.common['Authorization']
      }
      setLoading(false)
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
    await signInWithEmailAndPassword(auth, email, password)
  }

  const signOut = async () => {
    await firebaseSignOut(auth)
  }

  return (
    <AuthContext.Provider value={{ user, token, loading, configured: firebaseConfigured, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
