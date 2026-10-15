export type RoleCode = 'REQUESTER' | 'APPROVER' | 'DEPARTMENT_HEAD' | 'FINANCE' | 'OPS' | 'ADMIN' | (string & {})

export type Status =
  | 'DRAFT'
  | 'PENDING_APPROVAL'
  | 'RETURNED'
  | 'REJECTED'
  | 'APPROVED'
  | 'OPS_RECEIVED'
  | 'PROCESSING'
  | 'INTERNAL_APPROVAL'
  | 'FOR_FINANCE'
  | 'COMPLETED'
  | 'CANCELLED'

export type FormKind = 'ITEMS' | 'PAYMENT' | 'EXPENSE'
export type Priority = 'LOW' | 'NORMAL' | 'HIGH' | 'URGENT'

/** A person's own settings (Settings page). */
export interface Preferences {
  email_action: boolean
  email_updates: boolean
  email_comments: boolean
  email_digest: boolean
  density: 'auto' | 'compact' | 'comfortable'
  motion: 'on' | 'off'
  page_size: 10 | 20 | 50
  landing: 'dashboard' | 'requests' | 'approvals'
}

export interface Me {
  id: string
  email: string
  first_name: string
  last_name: string
  name: string
  employee_id: string
  position: string
  department: string | null
  department_name: string
  approver_level_name: string
  roles: RoleCode[]
  heads_department: boolean
  /** Whether an e-signature is on file; needed to submit and to approve. */
  has_signature: boolean
  /** Colour theme id; '' is the default. */
  theme: string
  /** Signs in with Active Directory, so the password is not managed in the portal. */
  is_directory_user: boolean
  preferences: Preferences
}

export interface RequestType {
  id: string
  code: string
  name: string
  description: string
  number_prefix: string
  form_kind: FormKind
  requires_attachment: boolean
  is_active: boolean
}

export interface Named {
  id: string
  name: string
}

export interface DepartmentOption extends Named {
  code: string
}

export interface UserBrief extends Named {
  email: string
  position: string
  department_name: string
}

/** A colleague found by search. Someone from Active Directory who has never signed in has no id yet. */
export interface Colleague extends Omit<UserBrief, 'id'> {
  id: string | null
  directory_username?: string
}

export interface AuditRow {
  id: string
  created_at: string
  action: string
  message: string
  actor_name: string
  request_id: string | null
  request_number: string
  comments: string
  ip_address: string | null
  user_agent: string
}

/** Cash advances: a liquidation shows the balance; an advance shows its liquidation. */
export type AdvancePosition =
  | { role: 'liquidation'; advance_id: string; advance_number: string; advance_amount: string; spent: string; to_return: string; to_reimburse: string }
  | { role: 'advance'; released: boolean; liquidated: boolean; liquidation: { id: string; number: string; status_display: string; total_amount: string } | null }

export interface SystemConfig {
  company_name: string
  company_address: string
  has_logo: boolean
  currency_code: string
  currency_symbol: string
  allow_self_approval: boolean
  ops_sla_days: number
  max_upload_mb: number
  /** Days before an approver is reminded / administrators are told; 0 switches it off. */
  reminder_after_days: number
  escalate_after_days: number
  /** Stop submissions that exceed a department budget, instead of only warning. */
  block_over_budget: boolean
}

/** Out-of-office cover (Settings page). */
export interface Delegation {
  delegate: UserBrief | null
  until: string | null
  covering_for: string[]
}

/** A background job the server runs on a timetable (Administration > Automations). */
export interface Automation {
  key: string
  name: string
  description: string
  schedule: string
  enabled: boolean
  last_run_at: string | null
  last_status: '' | 'ok' | 'skipped' | 'failed'
  last_detail: string
  running: boolean
}

export interface Lookups {
  request_types: RequestType[]
  departments: DepartmentOption[]
  expense_categories: (Named & { is_active: boolean })[]
  ops_users: UserBrief[]
  /** Names of listed vendors, offered as suggestions for Payable To. */
  vendors: string[]
  config: SystemConfig
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface RequestSummary {
  id: string
  number: string
  type_code: string
  type_name: string
  form_kind: FormKind
  status: Status
  status_display: string
  priority: Priority
  summary: string
  requester_name: string
  department: string
  department_name: string
  total_amount: string
  current_handler: string
  date_needed: string | null
  ops_assignee: string | null
  ops_assignee_name: string
  is_overdue: boolean
  submitted_at: string | null
  approved_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export interface RequestLine {
  id?: string
  description: string
  remarks: string
  quantity: string | null
  unit_cost: string | null
  amount: string | null
  expense_date: string | null
  category: string | null
  category_name?: string
}

export interface Attachment {
  id: string
  original_name: string
  content_type: string
  size: number
  kind: string
  kind_display: string
  uploaded_by_name: string
  created_at: string
  previewable: boolean
  can_delete: boolean
}

export interface RequestBrief {
  id: string
  number: string
  type_code: string
  type_name: string
  status: Status
  status_display: string
  total_amount: string
}

export interface RequestPermissions {
  is_owner: boolean
  can_edit: boolean
  /** Submitting applies the requester's signature, so only the requester can. */
  can_submit: boolean
  /** Whoever prepared it for a colleague can send it to them to submit. */
  can_hand_over: boolean
  can_issue_po: boolean
  can_delete: boolean
  can_cancel: boolean
  can_decide: boolean
  can_attach: boolean
  can_update_processing: boolean
  next_statuses: { status: Status; label: string }[]
}

export interface Vendor {
  id: string
  name: string
  tin: string
  address: string
  is_active: boolean
  request_count: number
}

export interface Budget {
  id: string
  department: string
  department_name: string
  year: number
  amount: string
  /** Total of the department's submitted requests for the year. */
  used: string
}

/** What the automatic checks found on a request. */
export interface RequestChecks {
  /** `id` is null when the viewer may not open the other request. */
  duplicates: { id: string | null; number: string; type_name: string; status_display: string; total_amount: string; submitted_at: string | null; reason: string }[]
  /** Figures are present only for people who decide or account for spending. */
  budget: { year: number; department: string; over: boolean; amount?: string; used?: string; this_request?: string; remaining?: string } | null
  unlisted_payee: boolean
  /** The requester's other cash advances that were released and are not liquidated yet. */
  open_advances: { number: string; total_amount: string; completed_at: string | null }[]
}

export interface RequestDetail extends RequestSummary {
  purpose: string
  payable_to: string
  pr_reference: string
  po_number: string
  rr_number: string
  invoice_number: string
  posted: boolean | null
  revision: number
  requester_position: string
  prepared_by_name: string
  ops_received_at: string | null
  lines: RequestLine[]
  attachments: Attachment[]
  source_request: RequestBrief | null
  linked_requests: RequestBrief[]
  current_step: { name: string; level: string; needs_clarification: boolean; pending_since: string | null } | null
  permissions: RequestPermissions
  checks: RequestChecks
  advance: AdvancePosition | null
  requester_id: string
  /** Prepared by one person in another's name. */
  prepared_for_other: boolean
  po_date: string | null
  po_terms: string
  po_issued_by_name: string
}

export interface LinkablePr extends RequestBrief {
  department: string
  department_name: string
  requester_name: string
  summary: string
  lines: { description: string; remarks: string; amount: string }[]
}

export interface RequestDraftPayload {
  request_type?: string
  department?: string | null
  priority?: Priority
  purpose?: string
  date_needed?: string | null
  payable_to?: string
  /** Set when preparing the request for a colleague. */
  requester?: string | null
  source_request?: string | null
  pr_reference?: string
  po_number?: string
  rr_number?: string
  invoice_number?: string
  posted?: boolean | null
  lines?: Partial<RequestLine>[]
}

export type NodeState = 'done' | 'current' | 'upcoming' | 'rejected' | 'returned' | 'skipped' | 'cancelled'

export interface TimelineNode {
  key: string
  label: string
  state: NodeState
  detail: string
  actor: string
  actor_position: string
  at: string | null
  comments: string
  notes: { actor: string; at: string; text: string }[]
}

export interface Timeline {
  current: TimelineNode[]
  previous: { cycle: number; outcome: string; ended_at: string | null; nodes: TimelineNode[] }[]
}

export interface AuditEntry {
  id: string
  action: string
  message: string
  actor_name: string
  previous_status: string
  new_status: string
  comments: string
  ip_address?: string | null
  user_agent?: string
  created_at: string
}

export interface Comment {
  id: string
  body: string
  author_name: string
  author_position: string
  created_at: string
}

export interface Notification {
  id: string
  event: string
  title: string
  message: string
  request: string | null
  request_number: string
  is_read: boolean
  created_at: string
}

export interface RequestNotification {
  id: string
  event: string
  title: string
  recipient_name: string
  email_status: 'NOT_SENT' | 'PENDING' | 'SENT' | 'FAILED'
  emailed_at: string | null
  created_at: string
}

export interface RoutePreview {
  id: string
  name: string
  requires_ops_processing: boolean
  steps: { order: number; name: string; approver: string; level: string; after_ops: boolean }[]
}

export interface PendingApproval extends RequestSummary {
  step_name: string
  step_level: string
  pending_since: string | null
  needs_clarification: boolean
}

export interface ApprovalHistoryItem {
  id: string
  action: string
  action_display: string
  comments: string
  created_at: string
  step_name: string
  request: RequestBrief
}

export interface Dashboard {
  requester: Record<'total' | 'drafts' | 'pending' | 'approved' | 'returned' | 'rejected' | 'completed', number>
  approver: Record<'pending' | 'approved_today' | 'returned' | 'rejected', number> | null
  ops: Record<'new' | 'pending_processing' | 'in_process' | 'waiting_finance' | 'completed' | 'overdue', number> | null
  admin: Record<
    'total' | 'pending_approval' | 'ops_processing' | 'completed' | 'active_users' | 'active_workflows',
    number
  > | null
  activity: { month: string; label: string; count: number }[]
  overview: { date: string; label: string; counts: Record<string, number> }[]
  by_type: { code: string; name: string; count: number }[]
  insights: {
    created: { current: number; previous: number }
    completed: { current: number; previous: number }
    pending_over_3_days: number
    processing_overdue: number
  }
}

export interface ReportRow {
  /** The value the Analytics page filters by when this row is clicked. */
  key?: string
  label: string
  count: number
  amount: string | number
}

export interface ReportSummary {
  totals: Record<'requests' | 'amount' | 'completed' | 'rejected' | 'pending_approval' | 'reimbursement_total', number | string>
  by_department: ReportRow[]
  by_type: ReportRow[]
  by_payee: (ReportRow & { listed: boolean })[]
  by_status: (ReportRow & { status: Status })[]
  monthly: ReportRow[]
  /** By day for short periods, by month otherwise. */
  trend: { unit: 'day' | 'month'; points: { date: string; label: string; count: number; amount: string | number }[] }
  /** Headline numbers for the period of the same length just before; null when the period is open-ended. */
  previous: { requests: number; amount: string | number; completed: number } | null
  funnel: { submitted: number; approved: number; processed: number; completed: number }
  /** Empty unless the viewer is an administrator or Finance. */
  budgets: { key: string; label: string; year: number; amount: string; used: string }[]
  processing_time: {
    label: string
    completed: number
    avg_days_to_approve: number | null
    avg_days_to_complete: number | null
  }[]
}

// --- Administration ---
export interface AdminUser {
  id: string
  email: string
  first_name: string
  last_name: string
  name: string
  employee_id: string
  position: string
  department: string | null
  department_name: string
  approver_level: string | null
  approver_level_name: string
  roles: string[]
  is_active: boolean
  last_login: string | null
  is_directory_user: boolean
  directory_username: string | null
}

export interface Department {
  id: string
  code: string
  name: string
  head: string | null
  head_name: string
  is_active: boolean
  member_count: number
}

export interface Role {
  id: string
  code: string
  name: string
  description: string
  is_system: boolean
  user_count: number
}

export interface ApprovalLevel {
  id: string
  code: string
  name: string
  rank: number
}

export type ApproverType = 'DEPARTMENT_HEAD' | 'ROLE' | 'USER'

export interface WorkflowStep {
  id?: string
  order?: number
  name: string
  level: string | null
  level_name?: string
  approver_type: ApproverType
  role: string | null
  role_name?: string
  user: string | null
  user_name?: string
  /** Approves after OPS has processed the request. */
  after_ops?: boolean
}

export interface Workflow {
  id: string
  name: string
  description: string
  request_type: string
  request_type_name: string
  department: string | null
  department_name: string
  min_amount: string | null
  max_amount: string | null
  priority: number
  requires_ops_processing: boolean
  is_active: boolean
  steps: WorkflowStep[]
}

export interface NotificationTemplate {
  id: string
  event: string
  event_display: string
  subject: string
  body: string
  send_email: boolean
  is_active: boolean
  placeholders: string[]
}

export interface EmailSettings {
  configured: boolean
  backend: string
  host: string
  port: number
  username: string
  use_tls: boolean
  from_email: string
  frontend_url: string
}
