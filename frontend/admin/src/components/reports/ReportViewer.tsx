import { ReactNode } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Download, Loader2 } from 'lucide-react'

export interface ColumnDef<T> {
  key: keyof T
  label: string
  render?: (value: T[keyof T], row: T) => ReactNode
  className?: string
}

interface SummaryItem {
  label: string
  value: ReactNode
}

interface ReportViewerProps<T extends Record<string, unknown>> {
  title: string
  description?: string
  columns: ColumnDef<T>[]
  rows: T[]
  summary?: SummaryItem[]
  isLoading: boolean
  generatedAt?: string
  csvFilename?: string
  noRowsMessage?: string
}

function buildCsv<T extends Record<string, unknown>>(columns: ColumnDef<T>[], rows: T[]): string {
  const header = columns.map((c) => `"${c.label}"`).join(',')
  const dataRows = rows.map((row) =>
    columns
      .map((c) => {
        const val = row[c.key as string]
        const str = val === null || val === undefined ? '' : String(val)
        return `"${str.replace(/"/g, '""')}"`
      })
      .join(','),
  )
  return [header, ...dataRows].join('\n')
}

function downloadCsv(csv: string, filename: string) {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function ReportViewer<T extends Record<string, unknown>>({
  title,
  description,
  columns,
  rows,
  summary,
  isLoading,
  generatedAt,
  csvFilename = 'report.csv',
  noRowsMessage = 'No data for this report.',
}: ReportViewerProps<T>) {
  const handleDownload = () => {
    downloadCsv(buildCsv(columns, rows), csvFilename)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{title}</h1>
          {description && <p className="text-muted-foreground mt-1 text-sm">{description}</p>}
          {generatedAt && (
            <p className="text-muted-foreground mt-1 text-xs">
              Generated {new Date(generatedAt).toLocaleString()}
            </p>
          )}
        </div>
        <Button onClick={handleDownload} disabled={isLoading || rows.length === 0} variant="outline" size="sm">
          <Download className="mr-2 h-4 w-4" />
          Download CSV
        </Button>
      </div>

      {summary && summary.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {summary.map(({ label, value }) => (
            <Card key={label}>
              <CardHeader className="pb-1 pt-3">
                <CardTitle className="text-muted-foreground text-xs font-medium">{label}</CardTitle>
              </CardHeader>
              <CardContent className="pb-3 pt-0">
                <div className="text-xl font-bold">{value}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
            </div>
          ) : rows.length === 0 ? (
            <div className="text-muted-foreground py-16 text-center text-sm">{noRowsMessage}</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    {columns.map((col) => (
                      <th
                        key={String(col.key)}
                        className={`px-4 py-3 text-left font-medium ${col.className ?? ''}`}
                      >
                        {col.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr key={i} className="border-b last:border-0 hover:bg-muted/30">
                      {columns.map((col) => (
                        <td key={String(col.key)} className={`px-4 py-3 ${col.className ?? ''}`}>
                          {col.render
                            ? col.render(row[col.key as string], row)
                            : (row[col.key as string] ?? '—')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
