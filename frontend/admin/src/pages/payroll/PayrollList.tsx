import { Receipt } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function PayrollList() {
  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-3">
        <Receipt className="h-5 w-5 text-muted-foreground" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Payroll Reports</h1>
          <p className="text-sm text-muted-foreground">Employer payroll submissions</p>
        </div>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Payroll Report History</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Payroll reports are ingested via <code className="text-xs bg-muted px-1 py-0.5 rounded">POST /api/v1/employers/:id/payroll-reports</code> (JSON) or the CSV upload endpoint.
            This view will list all submitted reports with row counts, status, and error details.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
