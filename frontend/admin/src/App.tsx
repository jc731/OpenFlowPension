import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from 'react-oidc-context'
import { AppShell } from '@/components/layout/AppShell'
import Dashboard from '@/pages/Dashboard'
import MemberList from '@/pages/members/MemberList'
import MemberDetail from '@/pages/members/MemberDetail'
import EmployerList from '@/pages/employers/EmployerList'
import RetirementCaseList from '@/pages/retirement/RetirementCaseList'
import PayrollList from '@/pages/payroll/PayrollList'
import PayrollDetail from '@/pages/payroll/PayrollDetail'
import SystemConfig from '@/pages/config/SystemConfig'
import ApiKeys from '@/pages/config/ApiKeys'
import { setAuthToken } from '@/lib/api'

const AUTH_ENABLED = !!import.meta.env.VITE_KEYCLOAK_URL

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
})

const mainRoutes = (
  <>
    <Route path="/" element={<Dashboard />} />
    <Route path="/members" element={<MemberList />} />
    <Route path="/members/:id" element={<MemberDetail />} />
    <Route path="/employers" element={<EmployerList />} />
    <Route path="/retirement" element={<RetirementCaseList />} />
    <Route path="/payroll" element={<PayrollList />} />
    <Route path="/payroll/:id" element={<PayrollDetail />} />
    <Route path="/config" element={<SystemConfig />} />
    <Route path="/api-keys" element={<ApiKeys />} />
  </>
)

// Only rendered when AUTH_ENABLED — safe to call useAuth() here
function AuthGate() {
  const auth = useAuth()

  useEffect(() => {
    setAuthToken(auth.user?.access_token ?? null)
    return () => setAuthToken(null)
  }, [auth.user?.access_token])

  if (auth.isLoading) {
    return <div className="flex h-screen items-center justify-center text-muted-foreground">Signing in…</div>
  }

  if (!auth.isAuthenticated) {
    auth.signinRedirect()
    return null
  }

  return <AppShell authUser={auth.user ?? undefined} onLogout={() => auth.signoutRedirect()} />
}

// Wraps AuthProvider inside BrowserRouter so onSigninCallback can use useNavigate
function AuthProviderWrapper({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()

  if (!AUTH_ENABLED) return <>{children}</>

  return (
    <AuthProvider
      authority={`${import.meta.env.VITE_KEYCLOAK_URL}/realms/${import.meta.env.VITE_KEYCLOAK_REALM ?? 'openflow'}`}
      client_id={import.meta.env.VITE_KEYCLOAK_CLIENT_ID ?? 'openflow-admin'}
      redirect_uri={`${window.location.origin}/auth/callback`}
      post_logout_redirect_uri={window.location.origin}
      scope="openid profile email"
      onSigninCallback={() => navigate('/', { replace: true })}
    >
      {children}
    </AuthProvider>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProviderWrapper>
          <Routes>
            {/* Callback landing — AuthProvider processes the code here */}
            {AUTH_ENABLED && (
              <Route
                path="/auth/callback"
                element={<div className="flex h-screen items-center justify-center text-muted-foreground">Completing sign-in…</div>}
              />
            )}
            <Route element={AUTH_ENABLED ? <AuthGate /> : <AppShell />}>
              {mainRoutes}
            </Route>
          </Routes>
        </AuthProviderWrapper>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
