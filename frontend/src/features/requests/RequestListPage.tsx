import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Download, Plus, SlidersHorizontal, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { downloadFile } from '../../api/client'
import { requestsApi, type RequestQuery } from '../../api/requests'
import { Button, ButtonLink, Card, DatePicker, ErrorState, Input, Pagination, Select, Tabs } from '../../components/ui'
import { useUser } from '../../hooks/useAuth'
import { useDebounced, useIsDesktop, useLookups } from '../../hooks/useLookups'
import { errorMessage, useToast } from '../../hooks/useToast'
import { STATUS_OPTIONS } from '../../utils/format'
import { RequestTable } from './RequestTable'

const SCOPES = [
  { value: '', label: 'All Requests' },
  { value: 'mine', label: 'My Requests' },
  { value: 'drafts', label: 'Drafts' },
  { value: 'awaiting_me', label: 'Awaiting Me' },
] as const
const FILTER_KEYS = ['type', 'status', 'department', 'date_from', 'date_to', 'min_amount', 'max_amount'] as const

export function RequestListPage() {
  const PAGE_SIZE = useUser().preferences.page_size
  const [params, setParams] = useSearchParams()
  const lookups = useLookups()
  const isDesktop = useIsDesktop()
  const toast = useToast()
  const [search, setSearch] = useState(params.get('search') ?? '')
  const debouncedSearch = useDebounced(search)
  const activeFilters = FILTER_KEYS.filter((key) => params.get(key)).length
  const [showFilters, setShowFilters] = useState(activeFilters > 0)

  /** Filters live in the URL so a filtered list can be bookmarked or shared. */
  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== 'page') next.delete('page')
    setParams(next, { replace: true })
  }

  useEffect(() => {
    if ((params.get('search') ?? '') !== debouncedSearch) setParam('search', debouncedSearch)
    // Only the debounced text should trigger this.
  }, [debouncedSearch]) // oxlint-disable-line react-hooks/exhaustive-deps

  const page = Number(params.get('page') ?? 1)
  const scope = (params.get('scope') ?? '') as RequestQuery['scope']
  const query: RequestQuery = { scope, search: params.get('search') ?? '', page, page_size: PAGE_SIZE }
  for (const key of FILTER_KEYS) query[key] = params.get(key) ?? ''

  const list = useQuery({ queryKey: ['requests', 'list', query], queryFn: () => requestsApi.list(query), placeholderData: keepPreviousData })

  // The spreadsheet holds every request that matches the search and filters, not only this page.
  const [exporting, setExporting] = useState(false)
  const exportList = async () => {
    setExporting(true)
    try {
      const { page: _page, page_size: _size, ...filters } = query
      await downloadFile('/requests/export/', 'requests.xlsx', { ...filters, file_format: 'xlsx' })
    } catch (error) {
      toast.error(error)
    } finally {
      setExporting(false)
    }
  }

  const clearFilters = () => {
    const next = new URLSearchParams()
    if (scope) next.set('scope', scope)
    setSearch('')
    setParams(next, { replace: true })
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Requests</h1>
          <p>Search and track purchase requisitions, payment requests and reimbursements.</p>
        </div>
        <div className="row-wrap">
          <Button icon={<Download size={16} />} loading={exporting} disabled={!list.data?.count} onClick={() => void exportList()}>
            {isDesktop ? 'Export to Excel' : 'Export'}
          </Button>
          <ButtonLink to="/requests/new" variant="primary" icon={<Plus size={16} />}>Create Request</ButtonLink>
        </div>
      </div>

      <Tabs tabs={[...SCOPES]} value={scope ?? ''} onChange={(value) => setParam('scope', value)} />

      <Card>
        <div className="stack-sm">
          <div className="row">
            <div className="grow">
              <Input label="Search" hideLabel type="search" placeholder="Search by request number, requester, department…"
                     value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <Button icon={<SlidersHorizontal size={16} />} aria-expanded={showFilters} onClick={() => setShowFilters((v) => !v)}>
              {isDesktop ? 'Filters' : ''}{activeFilters > 0 ? ` (${activeFilters})` : ''}
            </Button>
          </div>
          {showFilters && (
            <>
              <div className="filters">
                <Select label="Request type" placeholder="All types" value={params.get('type') ?? ''}
                        onChange={(e) => setParam('type', e.target.value)}
                        options={(lookups?.request_types ?? []).map((t) => ({ value: t.code, label: t.name }))} />
                <Select label="Status" placeholder="All statuses" value={params.get('status') ?? ''}
                        onChange={(e) => setParam('status', e.target.value)}
                        options={[
                          ...STATUS_OPTIONS,
                          ...(params.get('status')?.includes(',') ? [{ value: params.get('status')!, label: 'Several statuses' }] : []),
                        ]} />
                <Select label="Department" placeholder="All departments" value={params.get('department') ?? ''}
                        onChange={(e) => setParam('department', e.target.value)}
                        options={(lookups?.departments ?? []).map((d) => ({ value: d.id, label: d.name }))} />
                <DatePicker label="Created from" value={params.get('date_from') ?? ''} onChange={(e) => setParam('date_from', e.target.value)} />
                <DatePicker label="Created to" value={params.get('date_to') ?? ''} onChange={(e) => setParam('date_to', e.target.value)} />
                <Input label="Min amount" type="number" inputMode="decimal" min="0" value={params.get('min_amount') ?? ''}
                       onChange={(e) => setParam('min_amount', e.target.value)} />
                <Input label="Max amount" type="number" inputMode="decimal" min="0" value={params.get('max_amount') ?? ''}
                       onChange={(e) => setParam('max_amount', e.target.value)} />
              </div>
              {(activeFilters > 0 || search) && (
                <div><Button size="sm" variant="ghost" icon={<X size={14} />} onClick={clearFilters}>Clear filters</Button></div>
              )}
            </>
          )}
        </div>
      </Card>

      <Card flush>
        {list.isError ? (
          <ErrorState message={errorMessage(list.error)} onRetry={() => void list.refetch()} />
        ) : (
          <>
            <RequestTable rows={list.data?.results} loading={list.isLoading} showRequester={scope !== 'mine' && scope !== 'drafts'} />
            {list.data && <Pagination page={page} pageSize={PAGE_SIZE} count={list.data.count} onChange={(p) => setParam('page', String(p))} />}
          </>
        )}
      </Card>
    </div>
  )
}
