import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Receipt, Upload, AlertCircle } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { payrollApi, employersApi } from '@/lib/api'
import { formatDate } from '@/lib/utils'

const statusVariant: Record<string, 'default' | 'secondary' | 'success' | 'warning' | 'destructive'> = {
  pending: 'secondary',
  processing: 'warning',
  completed: 'success',
  failed: 'destructive',
}

export default function PayrollList() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [selectedEmployer, setSelectedEmployer] = useState('')
  const [uploadNote, setUploadNote] = useState('')
  const [filterEmployer, setFilterEmployer] = useState('')

  const { data: reports, isLoading } = useQuery({
    queryKey: ['payroll-reports', filterEmployer],
    queryFn: () => payrollApi.list(filterEmployer ? { employer_id: filterEmployer } : undefined),
  })

  const { data: employers } = useQuery({
    queryKey: ['employers'],
    queryFn: () => employersApi.list(),
  })

  const upload = useMutation({
    mutationFn: async (file: File) => {
      if (!selectedEmployer) throw new Error('Select an employer first')
      return payrollApi.uploadCsv(selectedEmployer, file, uploadNote || undefined)
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['payroll-reports'] })
      toast.success(`Report submitted: ${res.data.row_count} rows`)
      setUploadNote('')
      if (fileRef.current) fileRef.current.value = ''
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) upload.mutate(file)
  }

  const errorReports = reports?.data.filter(r => r.error_count > 0) ?? []

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Receipt className="h-5 w-5 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Payroll Reports</h1>
            <p className="text-sm text-muted-foreground">
              {reports?.data.length ?? 0} reports · {errorReports.length > 0 && (
                <span className="text-destructive font-medium">{errorReports.length} with errors</span>
              )}
            </p>
          </div>
        </div>
      </div>

      {/* Upload card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Upload className="h-4 w-4" /> Submit Payroll Report
          </CardTitle>
          <CardDescription>
            Upload a CSV file or submit JSON via API. Required columns:
            {' '}<code className="text-xs bg-muted px-1 py-0.5 rounded">
              member_number, period_start, period_end, gross_earnings, employee_contribution, employer_contribution, days_worked
            </code>
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground font-medium">Employer</label>
            <select
              value={selectedEmployer}
              onChange={e => setSelectedEmployer(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <option value="">Select employer…</option>
              {employers?.data.map(e => (
                <option key={e.id} value={e.id}>{e.name}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1 flex-1 min-w-40">
            <label className="text-xs text-muted-foreground font-medium">Note (optional)</label>
            <Input
              placeholder="e.g. March 2025 payroll"
              value={uploadNote}
              onChange={e => setUploadNote(e.target.value)}
            />
          </div>
          <div>
            <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleFileChange} />
            <Button
              onClick={() => fileRef.current?.click()}
              disabled={!selectedEmployer || upload.isPending}
            >
              <Upload className="h-4 w-4" />
              {upload.isPending ? 'Uploading…' : 'Choose CSV'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Error summary */}
      {errorReports.length > 0 && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-4 flex gap-3">
            <AlertCircle className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-destructive">
                {errorReports.length} report{errorReports.length > 1 ? 's' : ''} contain row-level errors
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Errors are per-row — the report still completed. Review the detail view to identify affected members.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filter + table */}
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <label className="text-sm text-muted-foreground">Filter by employer:</label>
          <select
            value={filterEmployer}
            onChange={e => setFilterEmployer(e.target.value)}
            className="h-8 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <option value="">All employers</option>
            {employers?.data.map(e => (
              <option key={e.id} value={e.id}>{e.name}</option>
            ))}
          </select>
        </div>

        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Employer</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Rows</TableHead>
                <TableHead className="text-right">Applied</TableHead>
                <TableHead className="text-right">Errors</TableHead>
                <TableHead className="text-right">Skipped</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow><TableCell colSpan={9} className="text-center text-muted-foreground py-8">Loading…</TableCell></TableRow>
              )}
              {!isLoading && !reports?.data.length && (
                <TableRow><TableCell colSpan={9} className="text-center text-muted-foreground py-8">No payroll reports yet.</TableCell></TableRow>
              )}
              {reports?.data.map(r => {
                const employer = employers?.data.find(e => e.id === r.employer_id)
                return (
                  <TableRow key={r.id}>
                    <TableCell className="text-sm">{formatDate(r.created_at)}</TableCell>
                    <TableCell className="font-medium">{employer?.name ?? r.employer_id.slice(0, 8)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {r.source_format.toUpperCase()}
                      {r.source_filename && <span className="ml-1 text-xs">· {r.source_filename}</span>}
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusVariant[r.status] ?? 'secondary'}>{r.status}</Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">{r.row_count}</TableCell>
                    <TableCell className="text-right font-mono text-sm text-emerald-700">{r.processed_count}</TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {r.error_count > 0
                        ? <span className="text-destructive font-medium">{r.error_count}</span>
                        : <span className="text-muted-foreground">0</span>}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm text-muted-foreground">{r.skipped_count}</TableCell>
                    <TableCell>
                      <Button variant="ghost" size="sm" asChild>
                        <Link to={`/payroll/${r.id}`}>Detail</Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  )
}
