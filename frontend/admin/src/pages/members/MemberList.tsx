import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Plus, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { membersApi } from '@/lib/api'
import { formatDate } from '@/lib/utils'

const statusVariant: Record<string, 'default' | 'secondary' | 'success' | 'warning' | 'destructive'> = {
  active: 'success',
  terminated: 'secondary',
  inactive: 'secondary',
  annuitant: 'default',
  on_leave: 'warning',
  deceased: 'destructive',
}

export default function MemberList() {
  const [search, setSearch] = useState('')
  const { data, isLoading } = useQuery({
    queryKey: ['members'],
    queryFn: () => membersApi.list(),
  })

  const filtered = data?.data.filter(m =>
    !search ||
    `${m.first_name} ${m.last_name}`.toLowerCase().includes(search.toLowerCase()) ||
    m.member_number.toLowerCase().includes(search.toLowerCase())
  ) ?? []

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Members</h1>
          <p className="text-sm text-muted-foreground">{data?.data.length ?? 0} total members</p>
        </div>
        <Button asChild>
          <Link to="/members/new"><Plus className="h-4 w-4" /> New Member</Link>
        </Button>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search by name or member number…"
          className="pl-8"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Member #</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Cert Date</TableHead>
              <TableHead>Plan</TableHead>
              <TableHead className="w-16" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-8">Loading…</TableCell></TableRow>
            )}
            {!isLoading && filtered.length === 0 && (
              <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-8">No members found.</TableCell></TableRow>
            )}
            {filtered.map(m => (
              <TableRow key={m.id}>
                <TableCell className="font-medium">
                  <Link to={`/members/${m.id}`} className="hover:underline">
                    {m.first_name} {m.last_name}
                  </Link>
                </TableCell>
                <TableCell className="font-mono text-xs">{m.member_number}</TableCell>
                <TableCell>
                  <Badge variant={statusVariant[m.member_status] ?? 'secondary'}>
                    {m.member_status}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm">{formatDate(m.certification_date)}</TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {m.plan_choice_locked ? 'Locked' : 'Open'}
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="sm" asChild>
                    <Link to={`/members/${m.id}`}>View</Link>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
