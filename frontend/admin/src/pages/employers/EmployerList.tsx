import { useQuery } from '@tanstack/react-query'
import { Building2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { employersApi } from '@/lib/api'
import { formatDate } from '@/lib/utils'

export default function EmployerList() {
  const { data, isLoading } = useQuery({
    queryKey: ['employers'],
    queryFn: () => employersApi.list(),
  })

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-3">
        <Building2 className="h-5 w-5 text-muted-foreground" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Employers</h1>
          <p className="text-sm text-muted-foreground">{data?.data.length ?? 0} registered employers</p>
        </div>
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Code</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground py-8">Loading…</TableCell></TableRow>
            )}
            {!isLoading && !data?.data.length && (
              <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground py-8">No employers on file.</TableCell></TableRow>
            )}
            {data?.data.map(e => (
              <TableRow key={e.id}>
                <TableCell className="font-medium">{e.name}</TableCell>
                <TableCell className="font-mono text-xs">{e.employer_code}</TableCell>
                <TableCell>
                  <Badge variant={e.active ? 'success' : 'secondary'}>{e.active ? 'Active' : 'Inactive'}</Badge>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{formatDate(e.created_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
