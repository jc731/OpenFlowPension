import { Settings } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'

const configKeys = [
  { key: 'employment_types', description: 'Valid employment type codes (general_staff, academic, police_fire, other)' },
  { key: 'leave_types', description: 'Valid leave type codes (medical, personal, military, family, other)' },
  { key: 'service_credit_accrual_rule', description: 'Monthly floor or proportional percent time accrual rules by effective date' },
  { key: 'concurrent_employment_max_annual_credit', description: 'Cap on total service credit per calendar year across concurrent positions' },
  { key: 'fund_calculation_config', description: 'FundConfig overrides (tier cutoff, FAE window, COLA type, sick leave method, etc.)' },
  { key: 'cpi_u_annual', description: 'Annual CPI-U rates for Tier II COLA projection (one row per year)' },
]

export default function SystemConfig() {
  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-3">
        <Settings className="h-5 w-5 text-muted-foreground" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">System Configuration</h1>
          <p className="text-sm text-muted-foreground">Fund-level rules stored in system_configurations</p>
        </div>
      </div>

      <div className="grid gap-3">
        {configKeys.map(({ key, description }) => (
          <Card key={key}>
            <CardHeader className="py-4">
              <CardTitle className="text-sm font-mono">{key}</CardTitle>
              <CardDescription className="text-xs">{description}</CardDescription>
            </CardHeader>
            <CardContent className="pt-0 pb-4">
              <p className="text-xs text-muted-foreground">
                Managed via <code className="bg-muted px-1 py-0.5 rounded">system_configurations</code> table · effective_date versioned · JSONB value
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
