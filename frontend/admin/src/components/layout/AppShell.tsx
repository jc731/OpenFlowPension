import { Outlet } from 'react-router-dom'
import type { User as OidcUser } from 'oidc-client-ts'
import { Sidebar } from './Sidebar'
import { Toaster } from 'sonner'

interface AppShellProps {
  authUser?: OidcUser
  onLogout?: () => void
}

export function AppShell({ authUser, onLogout }: AppShellProps = {}) {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar
        displayName={authUser?.profile?.name}
        email={authUser?.profile?.email}
        onLogout={onLogout}
      />
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
      <Toaster position="top-right" richColors />
    </div>
  )
}
