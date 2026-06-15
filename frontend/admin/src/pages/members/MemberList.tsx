import { useState, useEffect, useRef } from 'react'
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

const STATUS_OPTIONS = ['', 'active', 'terminated', 'annuitant', 'on_leave', 'inactive', 'deceased']

export default function MemberList() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setDebouncedSearch(search), 300)
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [search])

  const { data, isLoading } = useQuery({
    queryKey: ['members', debouncedSearch, status],
    queryFn: () => membersApi.list({
      q: debouncedSearch || undefined,
      status: status || undefined,
      limit: 200,
    }),
  })

  const members = data?.data ?? []

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Members</h1>
          <p className="text-sm text-muted-foreground">{members.length} member{members.length !== 1 ? 's' : ''}{debouncedSearch || status ? ' matching filters' : ''}</p>
        </div>
        <Button asChild>
          <Link to="/members/new"><Plus className="h-4 w-4 mr-1" /> New Member</Link>
        </Button>
      </div>

      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by name or member number…"
            className="pl-8"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <select
          value={status}
          onChange={e => setStatus(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.filter(Boolean).map(s => (
            <option key={s} value={s}>{s.replace('_', ' ')}</option>
          ))}
        </select>
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
            {!isLoading && members.length === 0 && (
              <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-8">No members found.</TableCell></TableRow>
            )}
            {members.map(m => (
              <TableRow key={m.id}>
                <TableCell className="font-medium">
                  <Link to={`/members/${m.id}`} className="hover:underline">
                    {m.first_name} {m.last_name}
                  </Link>
                </TableCell>
                <TableCell className="font-mono text-xs">{m.member_number}</TableCell>
                <TableCell>
                  <Badge variant={statusVariant[m.member_status] ?? 'secondary'}>
                    {m.member_status.replace('_', ' ')}
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
