import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Banknote, Check, ClipboardCheck, HandCoins, Receipt, Save, Send, ShoppingCart } from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, downloadFile, openFile } from '../../api/client'
import { requestsApi } from '../../api/requests'
import {
  AttachmentList, Button, ButtonLink, Card, ConfirmationDialog, ErrorState, FileUpload, LoadingState, Select, Stepper,
} from '../../components/ui'
import { SignatureField } from '../../components/SignatureField'
import { useUser } from '../../hooks/useAuth'
import { useDebounced, useLookups } from '../../hooks/useLookups'
import { errorMessage, useToast } from '../../hooks/useToast'
import type { Attachment, LinkablePr, RequestDetail, RequestDraftPayload, RequestType } from '../../types'
import {
  emptyLine, hasErrors, totalAmount, validateDetails, validateLines, type DraftForm, type FieldErrors,
} from '../../utils/validation'
import { DetailsStep, LINE_NOUN, LinesStep, ReviewStep } from './wizard/steps'

const TYPE_ICONS: Record<string, ReactNode> = {
  PR: <ShoppingCart size={20} />,
  RFP: <Banknote size={20} />,
  REIM: <Receipt size={20} />,
  CA: <HandCoins size={20} />,
  LIQ: <ClipboardCheck size={20} />,
}
const ATTACHMENT_KINDS = [
  ['QUOTATION', 'Quotation'], ['SPECIFICATION', 'Specification'], ['VENDOR', 'Vendor document'],
  ['RECEIPT', 'Receipt'], ['INVOICE', 'Invoice'], ['IMAGE', 'Image'], ['OTHER', 'Other'],
].map(([value, label]) => ({ value, label }))

function blankForm(type: RequestType, department: string, payee: string): DraftForm {
  return {
    typeCode: type.code, formKind: type.form_kind, department, priority: 'NORMAL', purpose: '', dateNeeded: '',
    payableTo: type.form_kind === 'EXPENSE' ? payee : '', requesterId: null, requesterName: '',
    sourceRequest: null, prReference: '', poNumber: '',
    rrNumber: '', invoiceNumber: '', posted: null, lines: [emptyLine()],
  }
}

function fromRequest(req: RequestDetail): DraftForm {
  return {
    typeCode: req.type_code, formKind: req.form_kind, department: req.department, priority: req.priority,
    purpose: req.purpose, dateNeeded: req.date_needed ?? '', payableTo: req.payable_to,
    requesterId: req.prepared_for_other ? req.requester_id : null, requesterName: req.prepared_for_other ? req.requester_name : '',
    sourceRequest: req.source_request?.id ?? null, prReference: req.pr_reference, poNumber: req.po_number,
    rrNumber: req.rr_number, invoiceNumber: req.invoice_number, posted: req.posted,
    lines: req.lines.map((line) => ({
      description: line.description, remarks: line.remarks, quantity: line.quantity ?? '',
      unit_cost: line.unit_cost ?? '', amount: line.amount ?? '', expense_date: line.expense_date ?? '',
      category: line.category ?? '',
    })),
  }
}

const orNull = (value: string | null | undefined) => (value === '' || value == null ? null : value)

function toPayload(form: DraftForm, creating: boolean): RequestDraftPayload {
  return {
    ...(creating ? { request_type: form.typeCode } : {}),
    department: form.department || null,
    priority: form.priority as RequestDraftPayload['priority'],
    purpose: form.purpose,
    date_needed: orNull(form.dateNeeded),
    payable_to: form.payableTo,
    ...(form.requesterId ? { requester: form.requesterId } : {}),
    source_request: form.sourceRequest,
    pr_reference: form.sourceRequest ? '' : form.prReference,
    po_number: form.poNumber,
    rr_number: form.rrNumber,
    invoice_number: form.invoiceNumber,
    posted: form.posted,
    lines: form.lines.map((line) => ({
      description: line.description, remarks: line.remarks, quantity: orNull(line.quantity),
      unit_cost: orNull(line.unit_cost), amount: orNull(line.amount), expense_date: orNull(line.expense_date),
      category: orNull(line.category),
    })),
  }
}

/** Starts the wizard afresh whenever the address asks for a different request or request type. */
export function RequestWizardPage() {
  const { id } = useParams()
  const [searchParams] = useSearchParams()
  return <Wizard key={`${id ?? 'new'}|${searchParams.get('type') ?? ''}|${searchParams.get('pr') ?? ''}|${searchParams.get('advance') ?? ''}`} />
}

function Wizard() {
  const { id: editId } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const client = useQueryClient()
  const toast = useToast()
  const user = useUser()
  const lookups = useLookups()

  const existing = useQuery({ queryKey: ['requests', 'detail', editId], queryFn: () => requestsApi.get(editId!), enabled: !!editId })
  const [form, setForm] = useState<DraftForm | null>(null)
  const [requestId, setRequestId] = useState<string | null>(editId ?? null)
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [linkedPr, setLinkedPr] = useState<{ number: string; total_amount: string } | null>(null)
  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState<'save' | 'submit' | 'upload' | null>(null)
  const [detailErrors, setDetailErrors] = useState<FieldErrors>({})
  const [lineErrors, setLineErrors] = useState<{ lines: FieldErrors[]; form?: string }>({ lines: [] })
  const [serverIssues, setServerIssues] = useState<string[]>([])
  const [uploadKind, setUploadKind] = useState('OTHER')
  // Typed since the last save, and where the person was heading when asked to confirm leaving.
  const [dirty, setDirty] = useState(false)
  const [leaveTo, setLeaveTo] = useState<string | null>(null)

  // While there are unsaved changes: ask before following any link out of the form,
  // and let the browser warn before the tab is closed or reloaded.
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    const intercept = (event: MouseEvent) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      const anchor = (event.target as Element).closest?.('a[href]') as HTMLAnchorElement | null
      if (!anchor || anchor.target === '_blank' || anchor.origin !== window.location.origin) return
      const to = anchor.pathname + anchor.search
      if (to === window.location.pathname + window.location.search) return
      event.preventDefault()
      event.stopPropagation()
      setLeaveTo(to)
    }
    window.addEventListener('beforeunload', warn)
    document.addEventListener('click', intercept, true)
    return () => {
      window.removeEventListener('beforeunload', warn)
      document.removeEventListener('click', intercept, true)
    }
  }, [dirty])

  // Load an existing draft, or preselect the type from ?type=PR.
  useEffect(() => {
    if (form || !lookups) return
    if (editId) {
      if (!existing.data) return
      setForm(fromRequest(existing.data))
      setAttachments(existing.data.attachments)
      setLinkedPr(existing.data.source_request)
      setStep(1)
      return
    }
    const preset = lookups.request_types.find((t) => t.code === searchParams.get('type'))
    if (preset) {
      setForm(blankForm(preset, user.department ?? '', user.name))
      setStep(1)
    }
  }, [form, lookups, editId, existing.data, searchParams, user])

  const update = (patch: Partial<DraftForm>) => {
    setDirty(true)
    setForm((current) => (current ? { ...current, ...patch } : current))
  }

  const link = (pr: LinkablePr | null) => {
    if (!form) return
    if (!pr) {
      setLinkedPr(null)
      update({ sourceRequest: null })
      return
    }
    setLinkedPr(pr)
    const untouched = form.lines.every((line) => !line.description.trim() && !line.amount)
    update({
      sourceRequest: pr.id,
      department: pr.department,
      ...(form.typeCode === 'LIQ' && !form.purpose.trim() ? { purpose: pr.summary } : {}),
      // Carry the PR's items over as payment particulars, unless the user already typed their own.
      ...(form.formKind === 'PAYMENT' && untouched
        ? { lines: pr.lines.map((line) => ({ ...emptyLine(), description: line.description, remarks: line.remarks, amount: Number(line.amount) > 0 ? line.amount : '' })) }
        : {}),
    })
    toast.success(`Linked to ${pr.number}. Details were filled in for you.`)
  }

  /** Prepare the request for a colleague (or go back to making it one's own). */
  const chooseRequester = (person: { id: string | null; name: string; department_name: string } | null) => {
    if (!form || !lookups) return
    const name = person?.name ?? user.name
    const department = lookups.departments.find((d) => d.name === (person ? person.department_name : user.department_name))?.id
    if (form.typeCode === 'LIQ') setLinkedPr(null) // a cash advance belongs to one person
    update({
      requesterId: person?.id ?? user.id, requesterName: person ? name : '',
      ...(department ? { department } : {}),
      ...(form.formKind === 'EXPENSE' ? { payableTo: name } : {}),
      ...(form.typeCode === 'LIQ' ? { sourceRequest: null } : {}),
    })
  }

  // Arriving from a PR's "Create Request for Payment" button, or a cash advance's "Liquidate": link it straight away.
  const presetAdvance = editId ? null : searchParams.get('advance')
  const presetPr = editId ? null : searchParams.get('pr') ?? presetAdvance
  const [presetDone, setPresetDone] = useState(false)
  useEffect(() => {
    if (!presetPr || presetDone || !form || form.formKind === 'ITEMS') return
    setPresetDone(true)
    requestsApi.linkable(presetPr, presetAdvance ? 'advance' : undefined).then((matches) => {
      const pr = matches.find((match) => match.number === presetPr)
      if (pr) link(pr)
    }).catch(() => undefined)
    // `link` reads the current form; this runs once, right after the form is created.
  }, [presetPr, presetDone, form]) // oxlint-disable-line react-hooks/exhaustive-deps
  const kind = form?.formKind ?? 'ITEMS'
  // Prepared for a colleague: they submit it, so their signature (not mine) is the one that matters.
  const onBehalf = !!form?.requesterId && form.requesterId !== user.id
  const canChangeRequester = !editId || (!!existing.data && existing.data.revision === 0
    && (!existing.data.prepared_for_other || existing.data.requester_id !== user.id))
  const steps = ['Type', 'Details', LINE_NOUN[kind].title, 'Attachments', 'Review', 'Submit']
  const total = form ? totalAmount(kind, form.lines) : 0
  const type = lookups?.request_types.find((t) => t.code === form?.typeCode)

  const routeKey = useDebounced(`${form?.typeCode}|${form?.department}|${total.toFixed(2)}`, 400)
  const route = useQuery({
    queryKey: ['route-preview', routeKey],
    queryFn: () => requestsApi.routePreview(form!.typeCode, form!.department || null, total.toFixed(2)),
    enabled: !!form && step === 4,
  })

  const issues = useMemo(() => {
    if (!form || !type) return []
    const list = [...Object.values(validateDetails(form))]
    const lines = validateLines(form)
    if (lines.form) list.push(lines.form)
    lines.lines.forEach((errors, index) => {
      const messages = Object.values(errors)
      if (messages.length) list.push(`${LINE_NOUN[kind].one} ${index + 1}: ${messages.join(' ')}`)
    })
    if (type.requires_attachment && attachments.length === 0) {
      list.push(`At least one supporting document is required for a ${type.name}.`)
    }
    if (!onBehalf && !user.has_signature) list.push('Add your e-signature before submitting.')
    return list
  }, [form, type, kind, attachments.length, user.has_signature, onBehalf])

  if (editId && existing.isError) {
    return <div className="page"><ErrorState message={errorMessage(existing.error)} /></div>
  }
  if (!lookups || (editId && !form)) return <LoadingState />
  if (editId && existing.data && !existing.data.permissions.can_edit) {
    return <div className="page"><ErrorState message="This request can no longer be edited." /></div>
  }


  /** Save to the server (creating the draft the first time) and return its id. */
  const persist = async (): Promise<string> => {
    if (!form) throw new Error('No form')
    const saved = requestId
      ? await requestsApi.update(requestId, toPayload(form, false))
      : await requestsApi.create(toPayload(form, true))
    setRequestId(saved.id)
    setDirty(false)
    void client.invalidateQueries({ queryKey: ['requests'] })
    void client.invalidateQueries({ queryKey: ['dashboard'] })
    return saved.id
  }

  const run = async (kindOfWork: typeof busy, work: () => Promise<void>) => {
    setBusy(kindOfWork)
    setServerIssues([])
    try {
      await work()
    } catch (error) {
      if (error instanceof ApiError && Object.keys(error.errors).length) {
        setServerIssues(Object.values(error.errors).flat().map(String))
        window.scrollTo({ top: 0, behavior: 'smooth' })
      } else {
        toast.error(error)
      }
    } finally {
      setBusy(null)
    }
  }

  const saveDraft = () => run('save', async () => {
    const id = await persist()
    toast.success('Draft saved.')
    navigate(`/requests/${id}`)
  })

  const submit = () => run('submit', async () => {
    const id = await persist()
    const submitted = await requestsApi.submit(id)
    toast.success(`${submitted.number} submitted for approval.`)
    navigate(`/requests/${id}`)
  })

  const sendToRequester = () => run('submit', async () => {
    const id = await persist()
    await requestsApi.handOver(id)
    toast.success(`Sent to ${form?.requesterName}. They will review and submit it.`)
    navigate(`/requests/${id}`)
  })

  const next = () => {
    if (!form) return
    if (step === 1) {
      const errors = validateDetails(form)
      setDetailErrors(errors)
      if (hasErrors(errors)) return
    }
    if (step === 2) {
      const errors = validateLines(form)
      setLineErrors(errors)
      if (errors.form || hasErrors(errors.lines)) return
      // Attachments belong to a saved request, so the draft is saved before that step.
      void run('save', async () => {
        await persist()
        setStep(3)
      })
      return
    }
    setStep((current) => current + 1)
  }

  const upload = (files: File[]) => run('upload', async () => {
    const id = requestId ?? (await persist())
    for (const file of files) {
      try {
        const saved = await requestsApi.upload(id, file, uploadKind)
        setAttachments((current) => [...current, saved])
      } catch (error) {
        const message = error instanceof ApiError ? error.field('file') ?? error.message : 'Upload failed.'
        toast.error(new ApiError(400, `${file.name}: ${message}`))
      }
    }
  })

  return (
    <div className="page page-narrow">
      <div className="page-header">
        <div>
          <h1>{editId ? `Edit ${existing.data?.number === 'Draft' ? 'Draft' : existing.data?.number}` : 'Create Request'}</h1>
          <p>{type ? type.name : 'Choose what you need, then fill in the details.'}</p>
        </div>
        {form && step > 0 && <Button variant="ghost" icon={<Save size={16} />} loading={busy === 'save'} onClick={saveDraft}>Save Draft</Button>}
      </div>

      <Stepper steps={steps} current={busy === 'submit' ? 5 : step} />
      {serverIssues.length > 0 && (
        <div className="alert alert-danger" role="alert">
          <ul>{serverIssues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
        </div>
      )}

      {step === 0 && (
        <div>
          <h2>Select Request Type</h2>
          <p className="small secondary">Choose the type of request you need to create.</p>
        </div>
      )}
      {step === 0 && (
        <div className="choice-grid">
          {lookups.request_types.map((option) => (
            <button key={option.code} type="button" className="choice" aria-pressed={form?.typeCode === option.code}
                    disabled={!!editId}
                    onClick={() => {
                      if (form?.typeCode !== option.code) {
                        setForm(blankForm(option, user.department ?? '', user.name))
                        setLinkedPr(null)
                      }
                    }}>
              {form?.typeCode === option.code && <span className="choice-check" aria-hidden><Check size={14} strokeWidth={3} /></span>}
              <span className="choice-icon">{TYPE_ICONS[option.code] ?? <ShoppingCart size={20} />}</span>
              <span>
                <span className="strong" style={{ display: 'block' }}>{option.name}</span>
                <span className="small secondary">{option.description}</span>
              </span>
            </button>
          ))}
        </div>
      )}

      {form && step === 1 && (
        <DetailsStep form={form} update={update} errors={detailErrors} lookups={lookups} user={user} linkedPr={linkedPr} onLink={link}
                     onRequester={chooseRequester} canChangeRequester={canChangeRequester} />
      )}
      {form && step === 2 && (
        <LinesStep form={form} update={update} errors={lineErrors.lines} formError={lineErrors.form} lookups={lookups} />
      )}
      {form && step === 3 && (
        <Card title="Supporting Documents">
          <div className="stack">
            <p className="small secondary">
              {type?.requires_attachment
                ? 'Attach your receipts. At least one document is required.'
                : 'Attach quotations, specifications or other supporting files. Optional.'}
            </p>
            <Select label="Document type" value={uploadKind} onChange={(e) => setUploadKind(e.target.value)} options={ATTACHMENT_KINDS} />
            <FileUpload onFiles={upload} busy={busy === 'upload'} maxMb={lookups.config.max_upload_mb} />
            <AttachmentList
              attachments={attachments}
              onOpen={(file) => void openFile(requestsApi.attachmentPath(requestId!, file.id), { inline: 1 }).catch(toast.error)}
              onDownload={(file) => void downloadFile(requestsApi.attachmentPath(requestId!, file.id), file.original_name).catch(toast.error)}
              onRemove={(file) => void requestsApi.removeAttachment(requestId!, file.id)
                .then(() => setAttachments((current) => current.filter((a) => a.id !== file.id)))
                .catch(toast.error)}
            />
          </div>
        </Card>
      )}
      {form && step === 4 && (
        <ReviewStep form={form} lookups={lookups} user={user} attachmentCount={attachments.length}
                    route={route.data?.route} routeLoading={route.isLoading} issues={issues}
                    advance={form.typeCode === 'LIQ' ? linkedPr : null} />
      )}
      {form && step === 4 && onBehalf && (
        <div className="callout callout-action">
          <strong>{form.requesterName} submits this request</strong>
          <span className="small secondary">It carries their e-signature, so it is sent to them to review and submit. You can keep editing it until they do.</span>
        </div>
      )}
      {form && step === 4 && !onBehalf && (
        <Card title="Your E-signature">
          <SignatureField purpose="Submitting applies this signature to the request and its printed form." />
        </Card>
      )}

      {step === 0 && (
        <div className="action-bar">
          <ButtonLink to="/requests">Cancel</ButtonLink>
          <Button variant="primary" disabled={!form} onClick={() => setStep(1)}>Next<ArrowRight size={16} /></Button>
        </div>
      )}
      {step > 0 && (
        <div className="action-bar">
          <Button icon={<ArrowLeft size={16} />} disabled={!!busy || (step === 1 && !!editId)} onClick={() => setStep(step - 1)}>Back</Button>
          {step < 4 ? (
            <Button variant="primary" loading={busy === 'save'} disabled={!!busy} onClick={next}>
              Next<ArrowRight size={16} />
            </Button>
          ) : onBehalf ? (
            <Button variant="primary" icon={<Send size={16} />} loading={busy === 'submit'} disabled={!!busy} onClick={sendToRequester}>
              Send to {form?.requesterName}
            </Button>
          ) : (
            <Button variant="primary" icon={<Send size={16} />} loading={busy === 'submit'}
                    disabled={!!busy || issues.length > 0 || !route.data?.route} onClick={submit}>
              Submit Request
            </Button>
          )}
        </div>
      )}
      {leaveTo && (
        <ConfirmationDialog title="Leave without saving?" confirmLabel="Leave" danger
                            message="What you typed since the last save will be lost. Choose Cancel, then Save Draft, to keep it."
                            onConfirm={() => {
                              setDirty(false)
                              navigate(leaveTo)
                            }}
                            onClose={() => setLeaveTo(null)} />
      )}
    </div>
  )
}
