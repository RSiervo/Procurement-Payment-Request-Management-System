import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, CheckCheck } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { notificationsApi } from '../../api/misc'
import { Button, Card, EmptyState, LoadingState, Pagination, Tabs } from '../../components/ui'
import { useToast } from '../../hooks/useToast'
import type { Notification } from '../../types'
import { formatDateTime } from '../../utils/format'

export function NotificationsPage() {
  const client = useQueryClient()
  const navigate = useNavigate()
  const toast = useToast()
  const [filter, setFilter] = useState<'all' | 'unread'>('all')
  const [page, setPage] = useState(1)
  const list = useQuery({
    queryKey: ['notifications', 'list', filter, page],
    queryFn: () => notificationsApi.list({ page, is_read: filter === 'unread' ? false : undefined }),
  })
  const refresh = () => void client.invalidateQueries({ queryKey: ['notifications'] })

  const open = async (note: Notification) => {
    if (!note.is_read) await notificationsApi.read(note.id).catch(() => undefined)
    refresh()
    if (note.request) navigate(`/requests/${note.request}`)
  }

  const markAll = async () => {
    try {
      await notificationsApi.readAll()
      refresh()
    } catch (error) {
      toast.error(error)
    }
  }

  return (
    <div className="page page-narrow">
      <div className="page-header">
        <div>
          <h1>Notifications</h1>
          <p>Everything sent to you about requests and approvals. The same messages go to your email.</p>
        </div>
        <Button icon={<CheckCheck size={16} />} onClick={() => void markAll()}>Mark all as read</Button>
      </div>
      <Tabs value={filter} onChange={(value) => { setFilter(value); setPage(1) }}
            tabs={[{ value: 'all', label: 'All' }, { value: 'unread', label: 'Unread' }]} />
      <Card flush>
        {list.isLoading || !list.data ? <LoadingState /> : list.data.results.length === 0 ? (
          <EmptyState icon={<Bell size={20} />} title={filter === 'unread' ? "You're all caught up" : 'No notifications yet'} />
        ) : (
          <>
            {list.data.results.map((note) => (
              <button key={note.id} type="button" className="notification" data-unread={!note.is_read} onClick={() => void open(note)}>
                <span className="notification-dot" aria-label={note.is_read ? undefined : 'Unread'} />
                <span>
                  <span className="notification-title small" style={{ display: 'block' }}>{note.title}</span>
                  <span className="small secondary pre-wrap" style={{ display: 'block' }}>{note.message}</span>
                  <span className="xs muted">{formatDateTime(note.created_at)}</span>
                </span>
              </button>
            ))}
            <Pagination page={page} pageSize={20} count={list.data.count} onChange={setPage} />
          </>
        )}
      </Card>
    </div>
  )
}
