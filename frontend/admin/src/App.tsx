import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
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

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/members" element={<MemberList />} />
            <Route path="/members/:id" element={<MemberDetail />} />
            <Route path="/employers" element={<EmployerList />} />
            <Route path="/retirement" element={<RetirementCaseList />} />
            <Route path="/payroll" element={<PayrollList />} />
            <Route path="/payroll/:id" element={<PayrollDetail />} />
            <Route path="/config" element={<SystemConfig />} />
            <Route path="/api-keys" element={<ApiKeys />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
