import type {
  AdminUser, ApprovalLevel, AuditRow, Automation, Budget, Colleague, Dashboard, Delegation, Department, EmailSettings, Lookups, Me, Named, Notification,
  NotificationTemplate, Paginated, ReportSummary, RequestType, Role, SystemConfig, Vendor, Workflow, Preferences,
} from '../types'
import { api } from './client'

export const authApi = {
  me: () => api.get<Me>('/me/'),
  login: (email: string, password: string, remember = false) => api.post<Me>('/auth/login/', { email, password, remember }),
  branding: () => api.get<{ company_name: string; has_logo: boolean }>('/branding/'),
  logout: () => api.post<void>('/auth/logout/'),
  updateProfile: (payload: Pick<Me, 'first_name' | 'last_name'>) => api.patch<Me>('/me/', payload),
  updateTheme: (theme: string) => api.patch<Me>('/me/', { theme }),
  updatePreferences: (preferences: Partial<Preferences>) => api.patch<Me>('/me/', { preferences }),
  uploadSignature: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<Me>('/me/signature/', form)
  },
  removeSignature: () => api.delete('/me/signature/'),
  delegation: () => api.get<Delegation>('/me/delegation/'),
  setDelegation: (delegate: string | null, until: string | null, directoryUsername?: string) =>
    api.put<Delegation>('/me/delegation/', { delegate, until, directory_username: directoryUsername }),
  /** With `directory`, also people in Active Directory who have not signed in to the portal yet. */
  colleagues: (search: string, directory = false) =>
    api.get<Colleague[]>('/colleagues/', { search, ...(directory ? { directory: 1 } : {}) }),
  requestPasswordReset: (email: string) => api.post<{ detail: string }>('/auth/password-reset/', { email }),
  confirmPasswordReset: (uid: string, token: string, new_password: string) =>
    api.post<{ detail: string }>('/auth/password-reset/confirm/', { uid, token, new_password }),
  changePassword: (current_password: string, new_password: string) =>
    api.post<void>('/me/change-password/', { current_password, new_password }),
}

export const lookupsApi = { get: () => api.get<Lookups>('/lookups/') }
export const dashboardApi = { get: (days = 7) => api.get<Dashboard>('/dashboard/', { days }) }

export const notificationsApi = {
  list: (query: { page?: number; is_read?: boolean; page_size?: number }) =>
    api.get<Paginated<Notification>>('/notifications/', query),
  unreadCount: () => api.get<{ count: number }>('/notifications/unread-count/'),
  read: (id: string) => api.post<Notification>(`/notifications/${id}/read/`),
  readAll: () => api.post<void>('/notifications/read-all/'),
}

export type ReportFilters = { date_from?: string; date_to?: string; type?: string; department?: string; status?: string }

export const reportsApi = {
  summary: (filters: ReportFilters) => api.get<ReportSummary>('/reports/', filters),
}

/** CRUD helper for the small reference-data resources administrators manage. */
function resource<T extends { id: string }>(path: string) {
  return {
    list: () => api.get<T[]>(`/${path}/`),
    create: (payload: Partial<T>) => api.post<T>(`/${path}/`, payload),
    update: (id: string, payload: Partial<T>) => api.patch<T>(`/${path}/${id}/`, payload),
    remove: (id: string) => api.delete(`/${path}/${id}/`),
  }
}

export const adminApi = {
  users: {
    list: (query: { search?: string; page?: number; page_size?: number }) =>
      api.get<Paginated<AdminUser>>('/users/', query),
    create: (payload: Partial<AdminUser> & { password?: string }) => api.post<AdminUser>('/users/', payload),
    update: (id: string, payload: Partial<AdminUser> & { password?: string }) =>
      api.patch<AdminUser>(`/users/${id}/`, payload),
  },
  departments: resource<Department>('departments'),
  roles: resource<Role>('roles'),
  levels: resource<ApprovalLevel>('approval-levels'),
  workflows: resource<Workflow>('workflows'),
  categories: resource<Named & { is_active: boolean }>('expense-categories'),
  requestTypes: resource<RequestType>('request-types'),
  vendors: resource<Vendor>('vendors'),
  budgets: resource<Budget>('budgets'),
  templates: resource<NotificationTemplate>('notification-templates'),
  emailSettings: () => api.get<EmailSettings>('/email-settings/'),
  sendTestEmail: () => api.post<{ detail: string }>('/email-settings/'),
  auditLog: (query: { search?: string; action?: string; date_from?: string; date_to?: string; page?: number }) =>
    api.get<Paginated<AuditRow> & { actions: string[] }>('/audit-log/', query),
  automations: () => api.get<Automation[]>('/automations/'),
  setAutomation: (key: string, enabled: boolean) => api.patch<Automation>(`/automations/${key}/`, { enabled }),
  runAutomation: (key: string) => api.post<Automation>(`/automations/${key}/run/`),
  config: () => api.get<SystemConfig>('/system-config/'),
  updateConfig: (payload: Partial<SystemConfig> | FormData) => api.patch<SystemConfig>('/system-config/', payload),
}
