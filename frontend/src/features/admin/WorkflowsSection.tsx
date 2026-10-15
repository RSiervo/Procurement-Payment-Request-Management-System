import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { adminApi } from '../../api/misc'
import {
  Badge, Button, Card, Checkbox, ConfirmationDialog, EmptyState, Input, LoadingState, Modal, MoneyInput, Select, Textarea,
} from '../../components/ui'
import { useLookups } from '../../hooks/useLookups'
import { useToast } from '../../hooks/useToast'
import type { ApprovalLevel, ApproverType, Role, UserBrief, Workflow, WorkflowStep } from '../../types'
import { money } from '../../utils/format'
import { WorkflowFlow } from '../requests/WorkflowFlow'

const APPROVER_TYPES: { value: ApproverType; label: string }[] = [
  { value: 'DEPARTMENT_HEAD', label: "Head of the requester's department" },
  { value: 'ROLE', label: 'Anyone with a role' },
  { value: 'USER', label: 'A specific person' },
]

function describeRule(workflow: Workflow): string {
  const { min_amount: low, max_amount: high } = workflow
  const amount = low && high ? `${money(low)} to ${money(high)}` : low ? `${money(low)} and above` : high ? `up to ${money(high)}` : 'any amount'
  return `${workflow.department_name || 'All departments'} · ${amount}`
}

function stepDetail(step: WorkflowStep): string {
  return step.approver_type === 'ROLE' ? step.role_name ?? '' : step.approver_type === 'USER' ? step.user_name ?? '' : 'Department head'
}

type Draft = Omit<Workflow, 'id' | 'request_type_name' | 'department_name'> & { id?: string }

const blankStep = (afterOps = false): WorkflowStep => ({ name: '', level: null, approver_type: afterOps ? 'ROLE' : 'DEPARTMENT_HEAD', role: null, user: null, after_ops: afterOps })

const STAGES = [
  { value: 'before', label: 'Before OPS processing' },
  { value: 'after', label: 'After OPS processing' },
]

function WorkflowEditor({ initial, roles, levels, users, onClose }: {
  initial: Draft
  roles: Role[]
  levels: ApprovalLevel[]
  users: UserBrief[]
  onClose: (saved: boolean) => void
}) {
  const lookups = useLookups()
  const toast = useToast()
  const [draft, setDraft] = useState<Draft>(initial)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (patch: Partial<Draft>) => setDraft((current) => ({ ...current, ...patch }))
  const setStep = (index: number, patch: Partial<WorkflowStep>) => set({ steps: draft.steps.map((s, i) => (i === index ? { ...s, ...patch } : s)) })
  const move = (index: number, by: number) => {
    const steps = [...draft.steps]
    const [step] = steps.splice(index, 1)
    steps.splice(index + by, 0, step)
    set({ steps })
  }

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    const payload = {
      ...draft,
      department: draft.department || null,
      min_amount: draft.min_amount || null,
      max_amount: draft.max_amount || null,
      // Steps before OPS always run first, whatever order they were added in.
      steps: [...draft.steps.filter((s) => !s.after_ops), ...draft.steps.filter((s) => s.after_ops)]
        .map(({ name, level, approver_type, role, user, after_ops }) => ({
          name, level: level || null, approver_type, role: role || null, user: user || null,
          after_ops: !!after_ops && draft.requires_ops_processing,
        })),
    } as Partial<Workflow>
    try {
      if (draft.id) await adminApi.workflows.update(draft.id, payload)
      else await adminApi.workflows.create(payload)
      toast.success('Workflow saved. It applies to requests submitted from now on.')
      onClose(true)
    } catch (err) {
      const details = err instanceof ApiError ? Object.entries(err.errors).map(([key, value]) => `${key}: ${JSON.stringify(value)}`).join(' ') : ''
      setError(err instanceof ApiError ? `${err.message} ${details}` : 'Could not save the workflow.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={draft.id ? 'Edit workflow' : 'Add workflow'} wide onClose={() => onClose(false)}
           footer={<>
             <Button onClick={() => onClose(false)} disabled={busy}>Cancel</Button>
             <Button variant="primary" type="submit" form="workflow-form" loading={busy} disabled={draft.steps.length === 0}>Save workflow</Button>
           </>}>
      <form id="workflow-form" className="stack" onSubmit={save}>
        {error && <div className="alert alert-danger" role="alert">{error}</div>}
        <div className="form-grid">
          <Input label="Name" required maxLength={120} value={draft.name} onChange={(e) => set({ name: e.target.value })} />
          <Select label="Request type" required value={draft.request_type} onChange={(e) => set({ request_type: e.target.value })}
                  options={(lookups?.request_types ?? []).map((t) => ({ value: t.code, label: t.name }))} />
          <Textarea label="Description" className="span-2" rows={2} value={draft.description} onChange={(e) => set({ description: e.target.value })} />
        </div>

        <div>
          <h3>When does this workflow apply?</h3>
          <p className="small secondary">The most specific matching workflow is used: a department match beats “all departments”, then higher priority wins.</p>
        </div>
        <div className="form-grid">
          <Select label="Department" placeholder="All departments" value={draft.department ?? ''} onChange={(e) => set({ department: e.target.value })}
                  options={(lookups?.departments ?? []).map((d) => ({ value: d.id, label: d.name }))} />
          <Input label="Priority" type="number" value={draft.priority} hint="Higher wins when several workflows match."
                 onChange={(e) => set({ priority: Number(e.target.value) })} />
          <MoneyInput label="Amount from" prefix={lookups?.config.currency_symbol} value={draft.min_amount ?? ''} hint="Inclusive. Leave empty for no lower limit."
                      onChange={(e) => set({ min_amount: e.target.value })} />
          <MoneyInput label="Amount up to" prefix={lookups?.config.currency_symbol} value={draft.max_amount ?? ''} hint="Inclusive. Leave empty for no upper limit."
                      onChange={(e) => set({ max_amount: e.target.value })} />
          <Checkbox label="Send to OPS for processing" checked={draft.requires_ops_processing}
                    onChange={(e) => set({ requires_ops_processing: e.target.checked })} />
          <Checkbox label="Active" checked={draft.is_active} onChange={(e) => set({ is_active: e.target.checked })} />
        </div>

        <div>
          <h3>Approval steps, in order</h3>
          <p className="small secondary">
            Steps set to “Before OPS processing” are approved first. OPS then receives and processes the request, and the
            steps set to “After OPS processing” follow. The last step is the final signatory: its approval completes the request.
          </p>
        </div>
        {draft.steps.map((step, index) => (
          <div key={index} className="line-card">
            <div className="line-head">
              <span>Step {index + 1}</span>
              <div className="row" style={{ gap: 0 }}>
                <button type="button" className="icon-btn" aria-label="Move up" disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp size={16} /></button>
                <button type="button" className="icon-btn" aria-label="Move down" disabled={index === draft.steps.length - 1} onClick={() => move(index, 1)}><ArrowDown size={16} /></button>
                <button type="button" className="icon-btn" aria-label="Remove step" onClick={() => set({ steps: draft.steps.filter((_, i) => i !== index) })}><Trash2 size={16} /></button>
              </div>
            </div>
            <div className="form-grid">
              <Input label="Step name" required maxLength={80} value={step.name} placeholder="e.g. Department Head, Verified By"
                     hint="Shown on the timeline and the printed form." onChange={(e) => setStep(index, { name: e.target.value })} />
              <Select label="Approval level" placeholder="None" value={step.level ?? ''} onChange={(e) => setStep(index, { level: e.target.value })}
                      options={levels.map((l) => ({ value: l.id, label: l.name }))} />
              {draft.requires_ops_processing && (
                <Select label="When" value={step.after_ops ? 'after' : 'before'} options={STAGES}
                        onChange={(e) => setStep(index, { after_ops: e.target.value === 'after' })} />
              )}
              <Select label="Who approves" value={step.approver_type} options={APPROVER_TYPES}
                      onChange={(e) => setStep(index, { approver_type: e.target.value as ApproverType })} />
              {step.approver_type === 'ROLE' && (
                <Select label="Role" required placeholder="Select role" value={step.role ?? ''} onChange={(e) => setStep(index, { role: e.target.value })}
                        options={roles.map((r) => ({ value: r.id, label: r.name }))} />
              )}
              {step.approver_type === 'USER' && (
                <Select label="Person" required placeholder="Select person" value={step.user ?? ''} onChange={(e) => setStep(index, { user: e.target.value })}
                        options={users.map((u) => ({ value: u.id, label: `${u.name}${u.position ? ` — ${u.position}` : ''}` }))} />
              )}
            </div>
          </div>
        ))}
        <Button icon={<Plus size={16} />} onClick={() => set({ steps: [...draft.steps, blankStep(draft.steps.some((s) => s.after_ops))] })}>Add approval step</Button>
      </form>
    </Modal>
  )
}

export function WorkflowsSection({ roles, levels, users }: { roles: Role[]; levels: ApprovalLevel[]; users: UserBrief[] }) {
  const client = useQueryClient()
  const lookups = useLookups()
  const toast = useToast()
  const { data, isLoading } = useQuery({ queryKey: ['admin', 'workflows'], queryFn: adminApi.workflows.list })
  const [editing, setEditing] = useState<Draft | null>(null)
  const [removing, setRemoving] = useState<Workflow | null>(null)
  const refresh = () => void client.invalidateQueries({ queryKey: ['admin', 'workflows'] })

  const blank = (): Draft => ({
    name: '', description: '', request_type: lookups?.request_types[0]?.code ?? 'PR', department: null, min_amount: null,
    max_amount: null, priority: 0, requires_ops_processing: true, is_active: true, steps: [blankStep()],
  })

  if (isLoading || !data) return <LoadingState />
  const types = lookups?.request_types ?? []

  return (
    <div className="stack">
      <div className="row-wrap between">
        <p className="small secondary" style={{ maxWidth: '70ch' }}>
          Each request follows the workflow that matches its type, department and amount. Changes apply to requests submitted afterwards; requests already in approval keep the route they started with.
        </p>
        <Button variant="primary" icon={<Plus size={15} />} onClick={() => setEditing(blank())}>Add workflow</Button>
      </div>
      {types.map((type) => {
        const workflows = data.filter((w) => w.request_type === type.code)
        return (
          <Card key={type.code} title={type.name}>
            {workflows.length === 0 ? (
              <EmptyState title="No workflow configured" message={`${type.name} requests cannot be submitted until a workflow exists.`} />
            ) : (
              <div className="stack">
                {workflows.map((workflow) => (
                  <div key={workflow.id} className="stack-sm" style={{ paddingBottom: 16, borderBottom: '1px solid var(--border)' }}>
                    <div className="row between" style={{ alignItems: 'flex-start' }}>
                      <div>
                        <div className="row-wrap">
                          <strong>{workflow.name}</strong>
                          {!workflow.is_active && <Badge plain>Inactive</Badge>}
                        </div>
                        <div className="small secondary">{describeRule(workflow)}</div>
                      </div>
                      <div className="row" style={{ gap: 0 }}>
                        <button type="button" className="icon-btn" aria-label={`Edit ${workflow.name}`} onClick={() => setEditing(workflow)}><Pencil size={16} /></button>
                        <button type="button" className="icon-btn" aria-label={`Delete ${workflow.name}`} onClick={() => setRemoving(workflow)}><Trash2 size={16} /></button>
                      </div>
                    </div>
                    <WorkflowFlow horizontal ops={workflow.requires_ops_processing}
                                  steps={workflow.steps.map((step) => ({ name: step.name, detail: stepDetail(step), afterOps: step.after_ops }))} />
                  </div>
                ))}
              </div>
            )}
          </Card>
        )
      })}
      {editing && (
        <WorkflowEditor initial={editing} roles={roles} levels={levels} users={users}
                        onClose={(saved) => { setEditing(null); if (saved) refresh() }} />
      )}
      {removing && (
        <ConfirmationDialog title="Delete this workflow?" confirmLabel="Delete" danger
                            message={`“${removing.name}” will no longer be used for new requests. Requests already in approval are not affected.`}
                            onConfirm={async () => {
                              try {
                                await adminApi.workflows.remove(removing.id)
                                refresh()
                              } catch (error) { toast.error(error) }
                            }}
                            onClose={() => setRemoving(null)} />
      )}
    </div>
  )
}
