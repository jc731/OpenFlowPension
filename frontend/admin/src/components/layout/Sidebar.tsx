import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Users, Building2, FileText,
  Receipt, Settings, KeyRound, ChevronRight,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Separator } from '@/components/ui/separator'

const lobNav = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/members', icon: Users, label: 'Members' },
  { to: '/employers', icon: Building2, label: 'Employers' },
  { to: '/retirement', icon: FileText, label: 'Retirement Cases' },
  { to: '/payroll', icon: Receipt, label: 'Payroll Reports' },
]

const adminNav = [
  { to: '/config', icon: Settings, label: 'System Config' },
  { to: '/api-keys', icon: KeyRound, label: 'API Keys' },
]

function NavItem({ to, icon: Icon, label, end }: { to: string; icon: React.ElementType; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          'group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
          isActive
            ? 'bg-sidebar-primary text-sidebar-primary-foreground'
            : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
        )
      }
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="flex-1">{label}</span>
      <ChevronRight className="h-3 w-3 opacity-0 group-hover:opacity-50 transition-opacity" />
    </NavLink>
  )
}

export function Sidebar() {
  return (
    <aside className="flex h-screen w-56 shrink-0 flex-col border-r bg-sidebar">
      {/* Branding */}
      <div className="flex h-14 items-center border-b px-4">
        <span className="font-semibold text-sidebar-foreground tracking-tight">OpenFlow Pension</span>
      </div>

      {/* LOB navigation */}
      <nav className="flex-1 overflow-y-auto p-2 space-y-1">
        <p className="px-3 pb-1 pt-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Fund Operations
        </p>
        {lobNav.map((item) => <NavItem key={item.to} {...item} />)}

        <Separator className="my-3" />

        <p className="px-3 pb-1 text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Administration
        </p>
        {adminNav.map((item) => <NavItem key={item.to} {...item} />)}
      </nav>

      {/* Footer */}
      <div className="border-t p-3">
        <div className="flex items-center gap-2 rounded-md px-2 py-1.5">
          <div className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center text-xs font-medium text-primary">
            FA
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-sidebar-foreground truncate">Fund Admin</p>
            <p className="text-xs text-muted-foreground truncate">Development</p>
          </div>
        </div>
      </div>
    </aside>
  )
}
