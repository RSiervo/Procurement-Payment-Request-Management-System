import { useQuery } from '@tanstack/react-query'
import { BellRing, Building2, FileText, GitBranch, Layers, Mail, ScrollText, Settings, ShieldCheck, Store, Tags, Users, Wallet, Zap } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { adminApi } from '../../api/misc'
import { Badge, Select } from '../../components/ui'
import type { AdminUser, ApprovalLevel, Budget, Department, Named, NotificationTemplate, RequestType, Role, Vendor } from '../../types'
import { formatDateTime, money } from '../../utils/format'
import { AuditLogSection } from './AuditLogSection'
import { AutomationsSection } from './AutomationsSection'
import { CrudSection } from './CrudSection'
import { EmailSection, SystemSection } from './SettingsSections'
import { WorkflowsSection } from './WorkflowsSection'

const SECTIONS = [
  { group: 'People', value: 'users', label: 'Users', icon: <Users size={16} /> },
  { group: 'People', value: 'departments', label: 'Departments', icon: <Building2 size={16} /> },
  { group: 'People', value: 'roles', label: 'Roles', icon: <ShieldCheck size={16} /> },
  { group: 'People', value: 'levels', label: 'Approval Levels', icon: <Layers size={16} /> },
  { group: 'Requests', value: 'workflows', label: 'Approval Workflows', icon: <GitBranch size={16} /> },
  { group: 'Requests', value: 'types', label: 'Request Types', icon: <FileText size={16} /> },
  { group: 'Requests', value: 'categories', label: 'Expense Categories', icon: <Tags size={16} /> },
  { group: 'Requests', value: 'vendors', label: 'Vendors', icon: <Store size={16} /> },
  { group: 'Requests', value: 'budgets', label: 'Budgets', icon: <Wallet size={16} /> },
  { group: 'System', value: 'templates', label: 'Notification Templates', icon: <BellRing size={16} /> },
  { group: 'System', value: 'automations', label: 'Automations', icon: <Zap size={16} /> },
  { group: 'System', value: 'audit', label: 'Audit Log', icon: <ScrollText size={16} /> },
  { group: 'System', value: 'email', label: 'Email Settings', icon: <Mail size={16} /> },
  { group: 'System', value: 'system', label: 'System', icon: <Settings size={16} /> },
] as const
type TabKey = (typeof SECTIONS)[number]['value']
const GROUPS = ['People', 'Requests', 'System'] as const

const active = (value: boolean) => <Badge tone={value ? 'success' : 'neutral'}>{value ? 'Active' : 'Inactive'}</Badge>

function budgetUse(budget: Budget) {
  const amount = Number(budget.amount)
  const used = Number(budget.used)
  if (amount <= 0) return <Badge tone={used > 0 ? 'danger' : 'neutral'} plain>{used > 0 ? 'Over' : '—'}</Badge>
  const percent = Math.round((used / amount) * 100)
  return <Badge tone={percent > 100 ? 'danger' : percent >= 80 ? 'warning' : 'success'} plain>{percent}%</Badge>
}

export function AdminPage() {
  const [params, setParams] = useSearchParams()
  const tab = (SECTIONS.find((t) => t.value === params.get('tab'))?.value ?? 'users') as TabKey
  const choose = (value: string) => setParams({ tab: value }, { replace: true })

  // Option lists shared by several forms.
  const roles = useQuery({ queryKey: ['admin', 'roles', ''], queryFn: adminApi.roles.list }).data ?? []
  const levels = useQuery({ queryKey: ['admin', 'levels', ''], queryFn: adminApi.levels.list }).data ?? []
  const departments = useQuery({ queryKey: ['admin', 'departments', ''], queryFn: adminApi.departments.list }).data ?? []
  const users = useQuery({ queryKey: ['admin', 'users-all'], queryFn: () => adminApi.users.list({ page_size: 100 }) }).data?.results ?? []
  const userOptions = users.filter((u) => u.is_active).map((u) => ({ value: u.id, label: u.name }))
  const userBriefs = users.filter((u) => u.is_active).map((u) => ({ id: u.id, name: u.name, email: u.email, position: u.position, department_name: u.department_name }))

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Administration</h1>
          <p>Configure who can do what, and how requests are routed.</p>
        </div>
      </div>
      <div className="admin-layout">
        {/* Sections down the left on wide screens; a single dropdown on phones. */}
        <nav className="admin-nav" aria-label="Administration sections">
          {GROUPS.map((group) => (
            <div key={group} className="admin-nav-group">
              <span className="admin-nav-heading">{group}</span>
              {SECTIONS.filter((section) => section.group === group).map((section) => (
                <button key={section.value} type="button" className="admin-nav-item" aria-current={tab === section.value ? 'page' : undefined}
                        onClick={() => choose(section.value)}>
                  {section.icon}<span>{section.label}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>
        <Select label="Section" hideLabel className="admin-nav-select" value={tab} onChange={(e) => choose(e.target.value)}
                options={SECTIONS.map((section) => ({ value: section.value, label: `${section.group} · ${section.label}` }))} />
        <div className="admin-content">

      {tab === 'users' && (
        <CrudSection<AdminUser>
          title="Users" noun="User" queryKey="users" searchable
          description="People who sign in with their Windows account appear here automatically, with name, department and position kept in step with Active Directory. Add roles such as Finance, OPS or Approver here. Users are deactivated rather than deleted. Showing up to 100 matches; use search to narrow down."
          list={(search) => adminApi.users.list({ search, page_size: 100 }).then((page) => page.results)}
          create={(values) => adminApi.users.create(values)}
          update={(id, values) => adminApi.users.update(id, values)}
          blank={{ email: '', first_name: '', last_name: '', employee_id: '', position: '', department: '', approver_level: '', roles: ['REQUESTER'], is_active: true, password: '' }}
          columns={[
            { header: 'Name', render: (u) => <div><div className="strong">{u.name}</div><div className="xs muted">{u.email}</div></div> },
            { header: 'Account', render: (u) => <Badge tone={u.is_directory_user ? 'info' : 'neutral'} plain>{u.is_directory_user ? 'Active Directory' : 'Local'}</Badge> },
            { header: 'Department', render: (u) => <div><div>{u.department_name || '—'}</div><div className="xs muted">{u.position}</div></div> },
            { header: 'Roles', render: (u) => <div className="row-wrap">{u.roles.map((r) => <Badge key={r} plain>{r.replace(/_/g, ' ')}</Badge>)}</div> },
            { header: 'Level', render: (u) => u.approver_level_name || '—' },
            { header: 'Last sign-in', render: (u) => <span className="muted nowrap">{u.last_login ? formatDateTime(u.last_login) : 'Never'}</span> },
            { header: 'Status', render: (u) => active(u.is_active) },
          ]}
          card={(u) => (
            <>
              <div className="strong">{u.name}</div>
              <div className="xs muted">{u.email} · {u.department_name || 'No department'}</div>
              <div className="row-wrap">{u.roles.map((r) => <Badge key={r} plain>{r.replace(/_/g, ' ')}</Badge>)}{!u.is_active && active(false)}</div>
            </>
          )}
          fields={[
            { name: 'first_name', label: 'First name', required: true },
            { name: 'last_name', label: 'Last name', required: true },
            { name: 'email', label: 'Email', type: 'email', required: true },
            { name: 'employee_id', label: 'Employee ID' },
            { name: 'position', label: 'Position' },
            { name: 'department', label: 'Department', type: 'select', options: departments.map((d) => ({ value: d.id, label: d.name })) },
            { name: 'approver_level', label: 'Approver level', type: 'select', options: levels.map((l) => ({ value: l.id, label: l.name })) },
            { name: 'password', label: 'Password', type: 'password', hint: 'Local accounts only, at least 10 characters. Leave empty to keep the current one. Active Directory accounts use their Windows password.' },
            { name: 'roles', label: 'Roles', type: 'multiselect', options: roles.map((r) => ({ value: r.code, label: r.name })) },
            { name: 'is_active', label: 'Active (can sign in)', type: 'checkbox' },
          ]}
        />
      )}

      {tab === 'departments' && (
        <CrudSection<Department>
          title="Departments" noun="Department" queryKey="departments"
          description="The department head approves any workflow step assigned to “Head of the requester's department”."
          list={() => adminApi.departments.list()} create={adminApi.departments.create} update={adminApi.departments.update} remove={adminApi.departments.remove}
          blank={{ code: '', name: '', head: '', is_active: true }}
          columns={[
            { header: 'Code', render: (d) => <span className="strong">{d.code}</span> },
            { header: 'Name', render: (d) => d.name },
            { header: 'Head', render: (d) => d.head_name || <Badge tone="warning" plain>No head assigned</Badge> },
            { header: 'Members', align: 'right', render: (d) => d.member_count },
            { header: 'Status', render: (d) => active(d.is_active) },
          ]}
          card={(d) => (<><div className="strong">{d.name} <span className="muted">({d.code})</span></div><div className="xs muted">Head: {d.head_name || 'not assigned'} · {d.member_count} members</div></>)}
          fields={[
            { name: 'code', label: 'Code', required: true },
            { name: 'name', label: 'Name', required: true },
            { name: 'head', label: 'Department head', type: 'select', options: userOptions },
            { name: 'is_active', label: 'Active', type: 'checkbox' },
          ]}
        />
      )}

      {tab === 'roles' && (
        <CrudSection<Role>
          title="Roles" noun="Role" queryKey="roles"
          description="Built-in roles control access to parts of the application. Roles you add can be used as approvers in workflows."
          list={() => adminApi.roles.list()} create={adminApi.roles.create} update={adminApi.roles.update} remove={adminApi.roles.remove}
          canRemove={(r) => !r.is_system}
          blank={{ code: '', name: '', description: '' }}
          columns={[
            { header: 'Role', render: (r) => <div><div className="strong">{r.name}</div><div className="xs muted">{r.code}</div></div> },
            { header: 'Description', render: (r) => r.description },
            { header: 'Users', align: 'right', render: (r) => r.user_count },
            { header: 'Kind', render: (r) => <Badge plain>{r.is_system ? 'Built-in' : 'Custom'}</Badge> },
          ]}
          card={(r) => (<><div className="strong">{r.name}</div><div className="xs muted">{r.description}</div><div className="xs muted">{r.user_count} users · {r.is_system ? 'Built-in' : 'Custom'}</div></>)}
          fields={[
            { name: 'code', label: 'Code', required: true, hint: 'Letters, numbers and underscores, e.g. SENIOR_MANAGEMENT.', only: 'create' },
            { name: 'name', label: 'Name', required: true },
            { name: 'description', label: 'Description', wide: true },
          ]}
        />
      )}

      {tab === 'levels' && (
        <CrudSection<ApprovalLevel>
          title="Approval Levels" noun="Approval level" queryKey="levels"
          description="Levels label workflow steps and users (for example Department Head, Finance, Senior Management). A higher rank is more senior."
          list={() => adminApi.levels.list()} create={adminApi.levels.create} update={adminApi.levels.update} remove={adminApi.levels.remove}
          blank={{ code: '', name: '', rank: 1 }}
          columns={[
            { header: 'Rank', render: (l) => l.rank },
            { header: 'Name', render: (l) => <span className="strong">{l.name}</span> },
            { header: 'Code', render: (l) => l.code },
          ]}
          card={(l) => (<><div className="strong">{l.name}</div><div className="xs muted">Rank {l.rank} · {l.code}</div></>)}
          fields={[
            { name: 'code', label: 'Code', required: true },
            { name: 'name', label: 'Name', required: true },
            { name: 'rank', label: 'Rank', type: 'number', required: true },
          ]}
        />
      )}

      {tab === 'workflows' && <WorkflowsSection roles={roles} levels={levels} users={userBriefs} />}

      {tab === 'types' && (
        <CrudSection<RequestType>
          title="Request Types" noun="Request type" queryKey="types"
          description="Each type has its own form layout, so new types are added by a developer. Here you can rename a type, switch it off, or require attachments."
          list={() => adminApi.requestTypes.list()} update={adminApi.requestTypes.update}
          blank={{}}
          columns={[
            { header: 'Type', render: (t) => <div><div className="strong">{t.name}</div><div className="xs muted">{t.description}</div></div> },
            { header: 'Number format', render: (t) => <span className="num">{t.number_prefix}-YYYY-000001</span> },
            { header: 'Attachment', render: (t) => (t.requires_attachment ? 'Required' : 'Optional') },
            { header: 'Status', render: (t) => active(t.is_active) },
          ]}
          card={(t) => (<><div className="strong">{t.name}</div><div className="xs muted">{t.number_prefix}-YYYY-000001 · Attachment {t.requires_attachment ? 'required' : 'optional'}</div></>)}
          fields={[
            { name: 'name', label: 'Name', required: true },
            { name: 'description', label: 'Description', wide: true },
            { name: 'requires_attachment', label: 'Require at least one attachment', type: 'checkbox' },
            { name: 'is_active', label: 'Active (can be created)', type: 'checkbox' },
          ]}
        />
      )}

      {tab === 'categories' && (
        <CrudSection<Named & { is_active: boolean }>
          title="Expense Categories" noun="Category" queryKey="categories"
          list={() => adminApi.categories.list()} create={adminApi.categories.create} update={adminApi.categories.update} remove={adminApi.categories.remove}
          blank={{ name: '', is_active: true }}
          columns={[{ header: 'Name', render: (c) => <span className="strong">{c.name}</span> }, { header: 'Status', render: (c) => active(c.is_active) }]}
          card={(c) => (<div className="row-wrap"><span className="strong">{c.name}</span>{!c.is_active && active(false)}</div>)}
          fields={[{ name: 'name', label: 'Name', required: true }, { name: 'is_active', label: 'Active', type: 'checkbox' }]}
        />
      )}

      {tab === 'vendors' && (
        <CrudSection<Vendor>
          title="Vendors" noun="Vendor" queryKey="vendors"
          description="Suppliers and other payees. When a request's Payable To matches a name here it is linked to the vendor and spelled exactly as listed, so reports and duplicate checks are reliable. A payment request to a payee that is not listed is flagged to the approvers. Vendors that have requests cannot be deleted; deactivate them instead."
          list={() => adminApi.vendors.list()} create={adminApi.vendors.create} update={adminApi.vendors.update} remove={adminApi.vendors.remove}
          canRemove={(v) => v.request_count === 0}
          blank={{ name: '', tin: '', address: '', is_active: true }}
          columns={[
            { header: 'Name', render: (v) => <div><div className="strong">{v.name}</div><div className="xs muted">{v.address}</div></div> },
            { header: 'TIN', render: (v) => v.tin || '—' },
            { header: 'Requests', align: 'right', render: (v) => v.request_count },
            { header: 'Status', render: (v) => active(v.is_active) },
          ]}
          card={(v) => (<><div className="strong">{v.name}</div><div className="xs muted">{v.tin ? `TIN ${v.tin} · ` : ''}{v.request_count} requests</div>{!v.is_active && active(false)}</>)}
          fields={[
            { name: 'name', label: 'Name', required: true, wide: true },
            { name: 'tin', label: 'TIN' },
            { name: 'address', label: 'Address' },
            { name: 'is_active', label: 'Active (offered as a suggestion)', type: 'checkbox' },
          ]}
        />
      )}

      {tab === 'budgets' && (
        <CrudSection<Budget>
          title="Budgets" noun="Budget" queryKey="budgets"
          description="What each department may commit in a calendar year. “Committed” is the total of its submitted requests that were not rejected, returned or cancelled; a payment linked to a Purchase Requisition is not counted twice. Approvers, Finance and OPS see where each request leaves the budget. To stop over-budget requests from being submitted at all, switch that on under System."
          list={() => adminApi.budgets.list()} create={adminApi.budgets.create} update={adminApi.budgets.update} remove={adminApi.budgets.remove}
          blank={{ department: '', year: new Date().getFullYear(), amount: '' }}
          columns={[
            { header: 'Department', render: (b) => <span className="strong">{b.department_name}</span> },
            { header: 'Year', render: (b) => b.year },
            { header: 'Budget', align: 'right', render: (b) => money(b.amount) },
            { header: 'Committed', align: 'right', render: (b) => money(b.used) },
            { header: 'Used', render: (b) => budgetUse(b) },
          ]}
          card={(b) => (<><div className="strong">{b.department_name} · {b.year}</div><div className="xs muted">{money(b.used)} of {money(b.amount)}</div>{budgetUse(b)}</>)}
          fields={[
            { name: 'department', label: 'Department', type: 'select', required: true, options: departments.map((d) => ({ value: d.id, label: d.name })) },
            { name: 'year', label: 'Year', type: 'number', required: true },
            { name: 'amount', label: 'Budget amount', type: 'number', required: true },
          ]}
        />
      )}

      {tab === 'templates' && (
        <CrudSection<NotificationTemplate>
          title="Notification Templates" noun="Template" queryKey="templates"
          description="Wording of in-app notifications and emails. Placeholders such as {{ request_number }}, {{ requester }}, {{ department }}, {{ amount }}, {{ actor }}, {{ comments }} and {{ status }} are filled in automatically. Emails also include a details table and a View Request button."
          list={() => adminApi.templates.list()} update={adminApi.templates.update}
          blank={{}}
          columns={[
            { header: 'Event', render: (t) => <span className="strong">{t.event_display}</span> },
            { header: 'Subject', render: (t) => t.subject },
            { header: 'Email', render: (t) => (t.send_email ? 'Yes' : 'In-app only') },
            { header: 'Status', render: (t) => active(t.is_active) },
          ]}
          card={(t) => (<><div className="strong">{t.event_display}</div><div className="xs muted">{t.subject}</div><div className="row-wrap">{active(t.is_active)}{!t.send_email && <Badge plain>In-app only</Badge>}</div></>)}
          fields={[
            { name: 'subject', label: 'Subject', required: true, wide: true },
            { name: 'body', label: 'Message', type: 'textarea', required: true },
            { name: 'send_email', label: 'Also send by email', type: 'checkbox' },
            { name: 'is_active', label: 'Active', type: 'checkbox' },
          ]}
        />
      )}

      {tab === 'automations' && <AutomationsSection />}
      {tab === 'audit' && <AuditLogSection />}
      {tab === 'email' && <EmailSection />}
      {tab === 'system' && <SystemSection />}
        </div>
      </div>
    </div>
  )
}
