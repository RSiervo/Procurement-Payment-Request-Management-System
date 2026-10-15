import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Send } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { adminApi } from '../../api/misc'
import { Badge, Button, Card, Checkbox, Input, LoadingState } from '../../components/ui'
import { useToast } from '../../hooks/useToast'
import type { SystemConfig } from '../../types'

export function EmailSection() {
  const toast = useToast()
  const { data } = useQuery({ queryKey: ['admin', 'email'], queryFn: adminApi.emailSettings })
  const [busy, setBusy] = useState(false)
  if (!data) return <LoadingState />

  const test = async () => {
    setBusy(true)
    try {
      toast.success((await adminApi.sendTestEmail()).detail)
    } catch (error) {
      toast.error(error)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Email Settings" actions={<Badge tone={data.configured ? 'success' : 'warning'}>{data.configured ? 'SMTP configured' : 'Not configured'}</Badge>}>
      <div className="stack">
        {!data.configured && (
          <div className="alert alert-warning">
            No mail server is configured, so emails are written to the server log instead of being delivered. In-app notifications still work.
          </div>
        )}
        <dl className="dl">
          <div><dt>Delivery</dt><dd>{data.backend}</dd></div>
          <div><dt>SMTP host</dt><dd>{data.host || '—'}</dd></div>
          <div><dt>Port</dt><dd>{data.port}</dd></div>
          <div><dt>Username</dt><dd>{data.username || '—'}</dd></div>
          <div><dt>TLS</dt><dd>{data.use_tls ? 'Yes' : 'No'}</dd></div>
          <div><dt>From address</dt><dd>{data.from_email}</dd></div>
          <div className="span-all"><dt>Link address used in emails</dt><dd>{data.frontend_url}</dd></div>
        </dl>
        <p className="small secondary">
          These values come from the server's environment variables (EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, DEFAULT_FROM_EMAIL, FRONTEND_URL) so that credentials are never stored in the database. Change them on the server and restart the application.
        </p>
        <div><Button icon={<Send size={15} />} loading={busy} onClick={() => void test()}>Send test email to me</Button></div>
      </div>
    </Card>
  )
}

export function SystemSection() {
  const client = useQueryClient()
  const toast = useToast()
  const { data } = useQuery({ queryKey: ['admin', 'config'], queryFn: adminApi.config })
  const [form, setForm] = useState<SystemConfig | null>(null)
  const [logo, setLogo] = useState<File | null>(null)
  const [errors, setErrors] = useState<Record<string, string[]>>({})
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (data) setForm(data)
  }, [data])
  if (!form) return <LoadingState />
  const set = (patch: Partial<SystemConfig>) => setForm({ ...form, ...patch })

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setErrors({})
    try {
      const body = new FormData()
      for (const key of ['company_name', 'company_address', 'currency_code', 'currency_symbol', 'ops_sla_days', 'max_upload_mb'] as const) {
        body.append(key, String(form[key]))
      }
      body.append('allow_self_approval', form.allow_self_approval ? 'true' : 'false')
      body.append('block_over_budget', form.block_over_budget ? 'true' : 'false')
      if (logo) body.append('logo', logo)
      await adminApi.updateConfig(body)
      setLogo(null)
      toast.success('System configuration saved.')
      void client.invalidateQueries({ queryKey: ['admin', 'config'] })
      void client.invalidateQueries({ queryKey: ['lookups'] })
    } catch (error) {
      if (error instanceof ApiError) setErrors(error.errors)
      toast.error(error)
    } finally {
      setBusy(false)
    }
  }
  const err = (name: string) => errors[name]?.[0]

  return (
    <Card title="System Configuration">
      <form className="stack" onSubmit={save}>
        <div className="form-grid">
          <Input label="Company name" required value={form.company_name} error={err('company_name')} hint="Printed at the top of generated forms."
                 onChange={(e) => set({ company_name: e.target.value })} />
          <Input label="Company address" value={form.company_address} error={err('company_address')} onChange={(e) => set({ company_address: e.target.value })} />
          <Input label="Currency code" required maxLength={3} value={form.currency_code} error={err('currency_code')} onChange={(e) => set({ currency_code: e.target.value.toUpperCase() })} />
          <Input label="Currency symbol" required maxLength={4} value={form.currency_symbol} error={err('currency_symbol')} onChange={(e) => set({ currency_symbol: e.target.value })} />
          <Input label="OPS processing target (days)" type="number" min="1" required value={form.ops_sla_days} error={err('ops_sla_days')}
                 hint="Approved requests untouched for longer than this are flagged overdue." onChange={(e) => set({ ops_sla_days: Number(e.target.value) })} />
          <Input label="Maximum upload size (MB)" type="number" min="1" max="25" required value={form.max_upload_mb} error={err('max_upload_mb')}
                 onChange={(e) => set({ max_upload_mb: Number(e.target.value) })} />
          <div className="field span-2">
            <label className="field-label" htmlFor="logo-input">Company logo for printed forms</label>
            <input id="logo-input" type="file" accept="image/png,image/jpeg" onChange={(e) => setLogo(e.target.files?.[0] ?? null)} />
            <span className="field-hint">{form.has_logo ? 'A logo is uploaded. Choose a file to replace it.' : 'No logo uploaded; the company name is printed instead.'}</span>
            {err('logo') && <span className="field-error">{err('logo')}</span>}
          </div>
          <div className="span-2">
            <Checkbox label="Allow users to approve their own requests" checked={form.allow_self_approval}
                      onChange={(e) => set({ allow_self_approval: e.target.checked })} />
            <p className="xs muted">Leave this off unless company policy explicitly permits it. When off, a requester is never offered their own request for approval.</p>
          </div>
          <div className="span-2">
            <Checkbox label="Do not allow a request to be submitted when it exceeds the department's budget" checked={form.block_over_budget}
                      onChange={(e) => set({ block_over_budget: e.target.checked })} />
            <p className="xs muted">When off, an over-budget request can still be submitted; the approvers are warned and it is recorded in the audit trail. Applies only to departments with a budget set under Budgets.</p>
          </div>
        </div>
        <div><Button type="submit" variant="primary" loading={busy}>Save configuration</Button></div>
      </form>
    </Card>
  )
}
