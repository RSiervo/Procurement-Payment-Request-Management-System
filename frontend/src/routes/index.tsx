import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { ButtonLink, EmptyState, LoadingState } from '../components/ui'
import { AdminPage } from '../features/admin/AdminPage'
import { ApprovalsPage } from '../features/approvals/ApprovalsPage'
import { LoginPage } from '../features/auth/LoginPage'
import { ForgotPasswordPage, ResetPasswordPage } from '../features/auth/PasswordResetPages'
import { ProfilePage } from '../features/auth/ProfilePage'
import { SettingsPage } from '../features/auth/SettingsPage'
import { DashboardPage } from '../features/dashboard/DashboardPage'
import { NotificationsPage } from '../features/notifications/NotificationsPage'
import { OpsPage } from '../features/ops/OpsPage'
import { ReportsPage } from '../features/reports/ReportsPage'
import { RequestDetailPage } from '../features/requests/RequestDetailPage'
import { RequestListPage } from '../features/requests/RequestListPage'
import { RequestWizardPage } from '../features/requests/RequestWizardPage'
import { VerifyPage } from '../features/requests/VerifyPage'
import { useAuth } from '../hooks/useAuth'
import { AppLayout } from '../layouts/AppLayout'
import type { RoleCode } from '../types'

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <LoadingState />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return <>{children}</>
}

/** Hides a page from users without the role. The API enforces the same rule; this only avoids dead ends. */
function RequireRole({ roles, orHead, children }: { roles: RoleCode[]; orHead?: boolean; children: ReactNode }) {
  const { hasRole, user } = useAuth()
  if (hasRole(...roles) || (orHead && user?.heads_department)) return <>{children}</>
  return (
    <div className="page">
      <EmptyState title="You don't have access to this page" message="Ask an administrator if you think you should."
                  action={<ButtonLink to="/" variant="primary">Back to dashboard</ButtonLink>} />
    </div>
  )
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/verify/:id" element={<VerifyPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
        <Route index element={<DashboardPage />} />
        <Route path="requests" element={<RequestListPage />} />
        <Route path="requests/new" element={<RequestWizardPage />} />
        <Route path="requests/:id" element={<RequestDetailPage />} />
        <Route path="requests/:id/edit" element={<RequestWizardPage />} />
        <Route path="approvals" element={<ApprovalsPage />} />
        <Route path="ops" element={<RequireRole roles={['OPS']}><OpsPage /></RequireRole>} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="reports" element={<RequireRole roles={['ADMIN', 'OPS', 'FINANCE']} orHead><ReportsPage /></RequireRole>} />
        <Route path="admin" element={<RequireRole roles={['ADMIN']}><AdminPage /></RequireRole>} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={
          <div className="page">
            <EmptyState title="Page not found" action={<ButtonLink to="/" variant="primary">Back to dashboard</ButtonLink>} />
          </div>
        } />
      </Route>
    </Routes>
  )
}
