import { Link } from 'react-router-dom'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { BarChart3, AlertCircle, Users, Heart } from 'lucide-react'

const reports = [
  {
    to: '/reports/contribution-reconciliation',
    icon: BarChart3,
    title: 'Contribution Reconciliation',
    description: 'Employee and employer contributions aggregated by employer for a date range.',
    id: 'RP01',
  },
  {
    to: '/reports/delinquency',
    icon: AlertCircle,
    title: 'Delinquency',
    description: 'Invoices past due with outstanding balances as of a given date.',
    id: 'RP02',
  },
  {
    to: '/reports/membership-counts',
    icon: Users,
    title: 'Membership Counts',
    description: 'Current member count grouped by status.',
    id: 'RP03',
  },
  {
    to: '/reports/annuitants',
    icon: Heart,
    title: 'Annuitant Export',
    description: 'All annuitants and retired members with approved benefit amounts.',
    id: 'RP04',
  },
]

export default function ReportsIndex() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Reports</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Administrative reports. Each report returns structured data that can be downloaded as CSV.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {reports.map(({ to, icon: Icon, title, description, id }) => (
          <Link key={id} to={to}>
            <Card className="hover:bg-muted/50 cursor-pointer transition-colors">
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <Icon className="text-muted-foreground h-5 w-5" />
                  <CardTitle className="text-base">{title}</CardTitle>
                  <span className="text-muted-foreground ml-auto text-xs">{id}</span>
                </div>
              </CardHeader>
              <CardContent>
                <CardDescription>{description}</CardDescription>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
