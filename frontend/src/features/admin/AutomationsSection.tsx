import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Play } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { adminApi } from '../../api/misc'
import { Badge, Button, Card, DataTable, EmptyState, Input, LoadingState } from '../../components/ui'
import { useToast } from '../../hooks/useToast'
import type { Automation } from '../../types'
import { timeAgo } from '../../utils/format'

const STATUS: Record<Automation['last_status'], { tone: 'success' | 'warning' | 'danger' | 'neutral'; label: string }> = {
  ok: { tone: 'success', label: 'OK' },
  skipped: { tone: 'warning', label: 'Skipped' },
  failed: { tone: 'danger', label: 'Failed' },
  '': { tone: 'neutral', label: 'Not run yet' },
}

/** Background jobs the server runs by itself, and the waiting times that drive the approval chasers. */
export function AutomationsSection() {
  const client = useQueryClient()
  const toast = useToast()
  const jobs = useQuery({ queryKey: ['admin', 'automations'], queryFn: adminApi.automations, refetchInterval: 60_000 })
  const config = useQuery({ queryKey: ['admin', 'config'], queryFn: adminApi.config }).data
  const [days, setDays] = useState<{ reminder: string; escalate: string } | null>(null)
  const [errors, setErrors] = useState<Record<string, string[]>>({})
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    if (config) setDays({ reminder: String(config.reminder_after_days), escalate: String(config.escalate_after_days) })
  }, [config])

  const change = async (key: string, work: () => Promise<Automation>, done: (job: Automation) => void) => {
    setBusy(key)
    try {
      done(await work())
      void client.invalidateQueries({ queryKey: ['admin', 'automations'] })
    } catch (error) {
      toast.error(error)
    } finally {
      setBusy(null)
    }
  }
  const toggle = (job: Automation) =>
    void change(job.key, () => adminApi.setAutomation(job.key, !job.enabled),
                (saved) => toast.success(`${saved.name} switched ${saved.enabled ? 'on' : 'off'}.`))
  const runNow = (job: Automation) =>
    void change(job.key, () => adminApi.runAutomation(job.key), (ran) => {
      const text = `${ran.name}: ${ran.last_detail || STATUS[ran.last_status].label}`
      if (ran.last_status === 'failed') toast.error(text)
      else toast.success(text)
    })

  const saveDays = async (event: FormEvent) => {
    event.preventDefault()
    if (!days) return
    setBusy('days')
    setErrors({})
    try {
      await adminApi.updateConfig({ reminder_after_days: Number(days.reminder), escalate_after_days: Number(days.escalate) })
      toast.success('Waiting times saved.')
      void client.invalidateQueries({ queryKey: ['admin', 'config'] })
    } catch (error) {
      if (error instanceof ApiError) setErrors(error.errors)
      toast.error(error)
    } finally {
      setBusy(null)
    }
  }

  const status = (job: Automation) => (
    <Badge tone={job.running ? 'info' : STATUS[job.last_status].tone} plain>{job.running ? 'Running…' : STATUS[job.last_status].label}</Badge>
  )
  const actions = (job: Automation) => (
    <div className="row" style={{ justifyContent: 'flex-end', gap: 6 }}>
      <Button size="sm" icon={<Play size={14} />} loading={busy === job.key} disabled={busy !== null || job.running} onClick={() => runNow(job)}>Run now</Button>
      <Button size="sm" disabled={busy !== null} onClick={() => toggle(job)}>{job.enabled ? 'Turn off' : 'Turn on'}</Button>
    </div>
  )

  return (
    <div className="stack">
      <Card flush title="Automations">
        <div style={{ padding: 16, borderBottom: '1px solid var(--border)' }}>
          <p className="small secondary">
            The server runs these by itself. They work only while the scheduled task “PPMS Automations” is running on the server;
            if every job shows an old “last run”, check that task.
          </p>
        </div>
        <DataTable
          rows={jobs.data}
          loading={jobs.isLoading}
          rowKey={(job) => job.key}
          empty={<EmptyState title="No automations" />}
          columns={[
            { header: 'Automation', render: (job) => <div><div className="strong">{job.name}</div><div className="xs muted">{job.description}</div></div> },
            { header: 'Runs', render: (job) => <span className="nowrap">{job.schedule}</span> },
            { header: 'Last run', render: (job) => (
              <div>
                <div className="row" style={{ gap: 6 }}>{status(job)}<span className="xs muted nowrap">{job.last_run_at ? timeAgo(job.last_run_at) : ''}</span></div>
                {job.last_detail && <div className="xs muted">{job.last_detail}</div>}
              </div>
            ) },
            { header: 'State', render: (job) => <Badge tone={job.enabled ? 'success' : 'neutral'}>{job.enabled ? 'On' : 'Off'}</Badge> },
            { header: '', align: 'right', render: actions },
          ]}
          card={(job) => (
            <div className="stack-sm">
              <div className="row between"><span className="strong">{job.name}</span><Badge tone={job.enabled ? 'success' : 'neutral'}>{job.enabled ? 'On' : 'Off'}</Badge></div>
              <div className="xs muted">{job.description}</div>
              <div className="row-wrap">{status(job)}<span className="xs muted">{job.schedule}{job.last_run_at ? ` · ${timeAgo(job.last_run_at)}` : ''}</span></div>
              {job.last_detail && <div className="xs muted">{job.last_detail}</div>}
              {actions(job)}
            </div>
          )}
        />
      </Card>

      <Card title="Approval waiting times">
        {!days ? <LoadingState /> : (
          <form className="stack" onSubmit={saveDays}>
            <div className="form-grid">
              <Input label="Remind the approver after (days)" type="number" min="0" max="60" required value={days.reminder}
                     error={errors.reminder_after_days?.[0]} hint="Repeated each time this many days pass. 0 switches reminders off."
                     onChange={(e) => setDays({ ...days, reminder: e.target.value })} />
              <Input label="Tell administrators after (days)" type="number" min="0" max="90" required value={days.escalate}
                     error={errors.escalate_after_days?.[0]} hint="Sent once per approval step. 0 switches escalation off."
                     onChange={(e) => setDays({ ...days, escalate: e.target.value })} />
            </div>
            <div><Button type="submit" variant="primary" loading={busy === 'days'}>Save waiting times</Button></div>
          </form>
        )}
      </Card>
    </div>
  )
}
