import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BarChart3, Bell, Building2, CheckCircle2, CheckSquare, ChevronDown, ChevronLeft, ChevronRight, ClipboardList, Clock,
  FileEdit, FileText,
  GitBranch, Home, LayoutDashboard, List, LogOut, Mail, Menu, Moon, MoreHorizontal, PackageCheck,
  Plus, PlusCircle, Receipt, HandCoins, ClipboardCheck,
  Settings, ShoppingCart, SlidersHorizontal, Sun, UserRound, Users, Banknote,
} from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { notificationsApi } from '../api/misc'
import { approvalsApi } from '../api/requests'
import { Logo } from '../components/Logo'
import { Avatar, Drawer, Dropdown, EmptyState } from '../components/ui'
import { useAuth, useUser } from '../hooks/useAuth'
import { useLookups } from '../hooks/useLookups'
import { useTheme } from '../hooks/useTheme'
import type { Me, Notification } from '../types'
import { timeAgo } from '../utils/format'

interface NavLeaf {
  to: string
  label: string
  icon?: ReactNode
  count?: number
}

interface NavGroup {
  label: string
  icon: ReactNode
  children: NavLeaf[]
  /** Groups start open unless this is set. */
  startCollapsed?: boolean
}

type NavEntry = NavLeaf | NavGroup
const isGroup = (entry: NavEntry): entry is NavGroup => 'children' in entry

const SIDEBAR_KEY = 'portal-sidebar-collapsed'

const TYPE_ICON: Record<string, ReactNode> = {
  PR: <ShoppingCart size={15} />,
  RFP: <Banknote size={15} />,
  REIM: <Receipt size={15} />,
  CA: <HandCoins size={15} />,
  LIQ: <ClipboardCheck size={15} />,
}

/** The label under the user's name: their most senior role in plain words. */
function roleLabel(user: Me): string {
  const has = (code: string) => user.roles.includes(code)
  if (has('ADMIN')) return 'Administrator'
  if (has('OPS')) return 'OPS'
  if (has('FINANCE')) return 'Finance'
  if (user.heads_department || has('DEPARTMENT_HEAD')) return 'Department Head'
  if (has('APPROVER')) return 'Approver'
  return 'Employee'
}

function usePendingApprovals() {
  return useQuery({ queryKey: ['approvals', 'pending'], queryFn: approvalsApi.pending, refetchInterval: 60_000 })
}

function useNavigation(): NavEntry[] {
  const { hasRole, user } = useAuth()
  const lookups = useLookups()
  const { data: pending } = usePendingApprovals()
  const approver = hasRole('APPROVER', 'DEPARTMENT_HEAD', 'FINANCE') || user?.heads_department || (pending?.length ?? 0) > 0
  const reports = hasRole('ADMIN', 'OPS', 'FINANCE') || user?.heads_department

  const entries: NavEntry[] = [
    { to: '/', label: 'Dashboard', icon: <Home size={18} /> },
    {
      label: 'Requests',
      icon: <ClipboardList size={18} />,
      children: [
        { to: '/requests', label: 'All Requests', icon: <List size={15} /> },
        { to: '/requests?scope=mine', label: 'My Requests', icon: <FileText size={15} /> },
        { to: '/requests?status=PENDING_APPROVAL', label: 'Pending Approval', icon: <Clock size={15} /> },
        { to: '/requests?scope=drafts', label: 'Drafts', icon: <FileEdit size={15} /> },
        { to: '/requests?status=COMPLETED', label: 'Completed', icon: <CheckCircle2 size={15} /> },
      ],
    },
    {
      label: 'Create Request',
      icon: <PlusCircle size={18} />,
      children: (lookups?.request_types ?? []).map((type) => ({
        to: `/requests/new?type=${type.code}`, label: type.name, icon: TYPE_ICON[type.code] ?? <FileText size={15} />,
      })),
    },
  ]
  if (approver) entries.push({ to: '/approvals', label: 'Approvals', icon: <CheckSquare size={18} />, count: pending?.length })
  if (hasRole('OPS')) entries.push({ to: '/ops', label: 'OPS Processing', icon: <PackageCheck size={18} /> })
  entries.push({ to: '/notifications', label: 'Notifications', icon: <Bell size={18} /> })
  if (reports) entries.push({ to: '/reports', label: 'Reports', icon: <BarChart3 size={18} /> })
  if (hasRole('ADMIN')) {
    entries.push({
      label: 'Administration',
      icon: <Settings size={18} />,
      startCollapsed: true,
      children: [
        { to: '/admin?tab=users', label: 'Users', icon: <Users size={15} /> },
        { to: '/admin?tab=departments', label: 'Departments', icon: <Building2 size={15} /> },
        { to: '/admin?tab=workflows', label: 'Approval Workflows', icon: <GitBranch size={15} /> },
        { to: '/admin?tab=templates', label: 'Notification Templates', icon: <Mail size={15} /> },
        { to: '/admin?tab=system', label: 'System Settings', icon: <SlidersHorizontal size={15} /> },
      ],
    })
  }
  entries.push({ to: '/profile', label: 'Profile', icon: <UserRound size={18} /> })
  return entries
}

function NavContent({ onNavigate, collapsed = false }: { onNavigate?: () => void; collapsed?: boolean }) {
  const entries = useNavigation()
  const location = useLocation()
  const current = location.pathname + location.search
  // Collapsed rail: the group whose fly-out menu is open, and where to place it.
  const [flyout, setFlyout] = useState<{ label: string; top: number } | null>(null)
  const flyoutRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setFlyout(null) // close on navigation or when the rail expands
  }, [current, collapsed])

  useEffect(() => {
    if (!flyout) return
    const onDown = (event: MouseEvent) => {
      const target = event.target as HTMLElement
      if (!flyoutRef.current?.contains(target) && !target.closest('.nav-group-toggle')) setFlyout(null)
    }
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setFlyout(null)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [flyout])
  // Remembers only groups the user has toggled; the rest follow their default.
  const [toggled, setToggled] = useState<Record<string, boolean>>({})
  // Links that carry a query string, and the bare /requests list, must match exactly.
  const isActive = (to: string) => (to === '/' || to.includes('?') || to === '/requests' ? current === to : location.pathname.startsWith(to))

  const leaf = (item: NavLeaf, sub = false) => (
    <Link key={item.to} to={item.to} onClick={onNavigate}
          className={`nav-item ${sub ? 'nav-sub' : ''} ${sub && item.icon ? 'has-icon' : ''} ${isActive(item.to) ? 'active' : ''}`}
          aria-current={isActive(item.to) ? 'page' : undefined}
          title={collapsed && !sub ? item.label : undefined}>
      {item.icon}
      <span className="nav-label">{item.label}</span>
      {!!item.count && <span className="nav-count">{item.count}</span>}
    </Link>
  )

  if (collapsed) {
    const openGroup = entries.find((entry): entry is NavGroup => isGroup(entry) && entry.label === flyout?.label)
    return (
      <nav className="nav nav-rail" aria-label="Main">
        {entries.map((entry) => {
          if (!isGroup(entry)) return leaf(entry)
          const containsCurrent = entry.children.some((child) => isActive(child.to))
          const open = flyout?.label === entry.label
          return (
            <button key={entry.label} type="button" title={entry.label} aria-label={entry.label}
                    aria-haspopup="menu" aria-expanded={open}
                    className={`nav-item nav-group-toggle ${containsCurrent ? 'active' : ''}`}
                    onClick={(event) => setFlyout(open ? null : { label: entry.label, top: event.currentTarget.getBoundingClientRect().top })}>
              {entry.icon}
            </button>
          )
        })}
        {openGroup && flyout && (
          <div ref={flyoutRef} className="nav-flyout" role="menu" aria-label={openGroup.label}
               style={{ top: Math.min(flyout.top, window.innerHeight - 56 - openGroup.children.length * 40) }}>
            <div className="nav-flyout-title">{openGroup.label}</div>
            {openGroup.children.map((child) => leaf(child, true))}
          </div>
        )}
      </nav>
    )
  }

  return (
    <nav className="nav" aria-label="Main">
      {entries.map((entry) => {
        if (!isGroup(entry)) return leaf(entry)
        const containsCurrent = entry.children.some((child) => isActive(child.to))
        const open = toggled[entry.label] ?? (containsCurrent || !entry.startCollapsed)
        return (
          <div key={entry.label}>
            <button type="button" className="nav-item nav-group-toggle" aria-expanded={open}
                    onClick={() => setToggled((state) => ({ ...state, [entry.label]: !open }))}>
              {entry.icon}
              <span className="nav-label">{entry.label}</span>
              <ChevronDown className="nav-chevron" size={16} />
            </button>
            {open && entry.children.map((child) => leaf(child, true))}
          </div>
        )
      })}
    </nav>
  )
}

function NotificationBell() {
  const client = useQueryClient()
  const navigate = useNavigate()
  const { data: unread } = useQuery({ queryKey: ['notifications', 'unread'], queryFn: notificationsApi.unreadCount, refetchInterval: 60_000 })
  const { data: recent } = useQuery({ queryKey: ['notifications', 'recent'], queryFn: () => notificationsApi.list({ page_size: 6 }), refetchInterval: 60_000 })
  const count = unread?.count ?? 0

  const open = async (note: Notification) => {
    if (!note.is_read) {
      await notificationsApi.read(note.id).catch(() => undefined)
      void client.invalidateQueries({ queryKey: ['notifications'] })
    }
    navigate(note.request ? `/requests/${note.request}` : '/notifications')
  }

  return (
    <Dropdown
      label={count ? `Notifications, ${count} unread` : 'Notifications'}
      menuClassName="notification-panel"
      trigger={<><Bell size={20} />{count > 0 && <span className="dot">{count > 99 ? '99+' : count}</span>}</>}
    >
      <div className="row between" style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
        <strong className="small">Notifications</strong>
        <Link to="/notifications" className="small">View all</Link>
      </div>
      {recent?.results.length ? (
        recent.results.map((note) => (
          <button key={note.id} type="button" className="notification" data-unread={!note.is_read} onClick={() => open(note)}>
            <span className="notification-dot" />
            <span>
              <span className="notification-title small" style={{ display: 'block' }}>{note.title}</span>
              <span className="xs muted">{timeAgo(note.created_at)}</span>
            </span>
          </button>
        ))
      ) : (
        <EmptyState title="You're all caught up" icon={<Bell size={20} />} />
      )}
    </Dropdown>
  )
}

export function ThemeToggle() {
  const { theme, toggle } = useTheme()
  const next = theme === 'dark' ? 'light' : 'dark'
  return (
    <button type="button" className="icon-btn theme-toggle" onClick={toggle}
            aria-label={`Switch to ${next} mode`} title={`Switch to ${next} mode`}>
      <Moon className="icon-moon" size={20} />
      <Sun className="icon-sun" size={20} />
    </button>
  )
}

const QUICK_CREATE_ICONS: Record<string, ReactNode> = {
  PR: <ShoppingCart size={20} />,
  RFP: <Banknote size={20} />,
  REIM: <Receipt size={20} />,
}

/** Phone navigation: the most used destinations within thumb reach, with "create" in the middle. */
function TabBar({ onMore }: { onMore: () => void }) {
  const { pathname, search } = useLocation()
  const { data: pending } = usePendingApprovals()
  const types = useLookups()?.request_types ?? []
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    setCreating(false) // close after choosing a type, or on any other navigation
  }, [pathname, search])

  useEffect(() => {
    if (!creating) return
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setCreating(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [creating])
  const tab = (to: string, label: string, icon: ReactNode, active: boolean, count?: number) => (
    <Link to={to} className={`tabbar-item ${active ? 'active' : ''}`} aria-current={active ? 'page' : undefined}>
      {icon}
      {label}
      {!!count && <span className="dot">{count}</span>}
    </Link>
  )
  return (
    <>
      {creating && (
        <>
          <div className="quick-create-backdrop" onClick={() => setCreating(false)} />
          <div className="quick-create" id="quick-create-menu" role="menu" aria-label="Create a request">
            {types.map((type, index) => (
              // The option nearest the button appears first, then the ones above it.
              <Link key={type.code} to={`/requests/new?type=${type.code}`} role="menuitem" className="quick-create-item"
                    data-type={type.code} style={{ animationDelay: `${(types.length - 1 - index) * 60}ms` }}>
                <span className="quick-create-icon">{QUICK_CREATE_ICONS[type.code] ?? <Plus size={20} />}</span>
                {type.name}
              </Link>
            ))}
          </div>
        </>
      )}
      <nav className={`tabbar ${creating ? 'tabbar-raised' : ''}`} aria-label="Quick navigation">
        {tab('/', 'Home', <LayoutDashboard size={20} />, pathname === '/')}
        {tab('/requests', 'Requests', <ClipboardList size={20} />, pathname.startsWith('/requests'))}
        <div className="tabbar-create">
          <button type="button" className="tabbar-fab" aria-haspopup="menu" aria-expanded={creating} aria-controls="quick-create-menu"
                  aria-label={creating ? 'Close create menu' : 'Create a request'} onClick={() => setCreating((open) => !open)}>
            <Plus size={26} strokeWidth={2.4} />
          </button>
        </div>
        {tab('/approvals', 'Approvals', <CheckSquare size={20} />, pathname.startsWith('/approvals'), pending?.length)}
        <button type="button" className="tabbar-item" onClick={onMore}>
          <MoreHorizontal size={20} />
          More
        </button>
      </nav>
    </>
  )
}

export function AppLayout() {
  const user = useUser()
  const { logout } = useAuth()
  const lookups = useLookups()
  const location = useLocation()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_KEY) === '1'
    } catch {
      return false
    }
  })

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [location.pathname])

  const toggleSidebar = () => {
    setCollapsed((current) => {
      try {
        localStorage.setItem(SIDEBAR_KEY, current ? '0' : '1')
      } catch {
        // not remembered; still applies for this visit
      }
      return !current
    })
  }

  return (
    <div className={`app ${collapsed ? 'sidebar-collapsed' : ''}`}>
      <header className="topbar">
        <button type="button" className="icon-btn mobile-only" aria-label="Open menu" onClick={() => setDrawerOpen(true)}>
          <Menu size={22} />
        </button>
        <Link to="/" className="brand">
          <Logo available={lookups?.config.has_logo ?? false} />
          <span className="brand-name desktop-only">Procurement &amp; Payment <span className="brand-name-accent">Portal</span></span>
        </Link>
        <span className="grow" />
        <ThemeToggle />
        <NotificationBell />
        <Dropdown label="Account menu" triggerClassName="user-chip"
                  trigger={
                    <>
                      <Avatar name={user.name} />
                      <span className="user-chip-text"><strong>{user.name}</strong><span>{roleLabel(user)}</span></span>
                      <ChevronDown size={16} />
                    </>
                  }>
          <div style={{ padding: '8px 12px 10px', borderBottom: '1px solid var(--border)', marginBottom: 4 }}>
            <div className="strong small">{user.name}</div>
            <div className="xs muted truncate">{user.position || user.email}</div>
          </div>
          <Link to="/profile" className="dropdown-item" role="menuitem"><UserRound size={16} />Profile</Link>
          <Link to="/settings" className="dropdown-item" role="menuitem"><Settings size={16} />Settings</Link>
          <button type="button" className="dropdown-item" role="menuitem" onClick={() => void logout()}>
            <LogOut size={16} />Sign out
          </button>
        </Dropdown>
      </header>

      <aside className="sidebar">
        <button type="button" className="sidebar-collapse" onClick={toggleSidebar} aria-expanded={!collapsed}
                aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
        <NavContent collapsed={collapsed} />
      </aside>
      {drawerOpen && (
        <Drawer label="Main menu" onClose={() => setDrawerOpen(false)}>
          <div className="row" style={{ gap: 12, padding: '16px 16px 4px' }}>
            <Avatar name={user.name} />
            <div className="grow">
              <div className="strong small truncate">{user.name}</div>
              <div className="xs muted truncate">{roleLabel(user)}</div>
            </div>
          </div>
          <NavContent onNavigate={() => setDrawerOpen(false)} />
          <div style={{ padding: '0 12px 16px' }}>
            <button type="button" className="nav-item" onClick={() => void logout()}><LogOut size={18} />Sign out</button>
          </div>
        </Drawer>
      )}

      <main className="main"><Outlet /></main>
      <TabBar onMore={() => setDrawerOpen(true)} />
    </div>
  )
}
