import type {
  ApprovalHistoryItem, Attachment, AuditEntry, Comment, LinkablePr, Paginated, PendingApproval,
  RequestDetail, RequestDraftPayload, RequestNotification, RequestSummary, RoutePreview, Status, Timeline,
} from '../types'
import { api } from './client'

export type RequestQuery = {
  scope?: 'mine' | 'drafts' | 'awaiting_me' | 'ops' | ''
  search?: string
  type?: string
  status?: string
  department?: string
  priority?: string
  requester?: string
  ops_assignee?: string
  date_from?: string
  date_to?: string
  min_amount?: string
  max_amount?: string
  overdue?: boolean
  unassigned?: boolean
  ordering?: string
  page?: number
  page_size?: number
}

export type Decision = 'approve' | 'reject' | 'return' | 'clarify'

export const requestsApi = {
  list: (query: RequestQuery) => api.get<Paginated<RequestSummary>>('/requests/', query),
  get: (id: string) => api.get<RequestDetail>(`/requests/${id}/`),
  create: (payload: RequestDraftPayload) => api.post<RequestDetail>('/requests/', payload),
  update: (id: string, payload: RequestDraftPayload) => api.patch<RequestDetail>(`/requests/${id}/`, payload),
  remove: (id: string) => api.delete(`/requests/${id}/`),
  submit: (id: string) => api.post<RequestDetail>(`/requests/${id}/submit/`),
  decide: (id: string, decision: Decision, comments: string) =>
    api.post<RequestDetail>(`/requests/${id}/${decision}/`, { comments }),
  cancel: (id: string, comments: string) => api.post<RequestDetail>(`/requests/${id}/cancel/`, { comments }),
  timeline: (id: string) => api.get<Timeline>(`/requests/${id}/timeline/`),
  auditLog: (id: string) => api.get<AuditEntry[]>(`/requests/${id}/audit-log/`),
  notifications: (id: string) => api.get<RequestNotification[]>(`/requests/${id}/notifications/`),
  comments: (id: string) => api.get<Comment[]>(`/requests/${id}/comments/`),
  addComment: (id: string, body: string) => api.post<Comment>(`/requests/${id}/comments/`, { body }),
  upload: (id: string, file: File, kind: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('kind', kind)
    return api.post<Attachment>(`/requests/${id}/attachments/`, form)
  },
  removeAttachment: (id: string, attachmentId: string) => api.delete(`/requests/${id}/attachments/${attachmentId}/`),
  attachmentPath: (id: string, attachmentId: string) => `/requests/${id}/attachments/${attachmentId}/`,
  pdfPath: (id: string) => `/requests/${id}/pdf/`,
  /** Approved PRs to pay against, or with kind "advance" the person's cash advances still to be liquidated. */
  linkable: (search: string, kind?: 'advance', requester?: string | null) =>
    api.get<LinkablePr[]>('/requests/linkable/', { search, ...(kind ? { kind } : {}), ...(requester ? { requester } : {}) }),
  handOver: (id: string) => api.post<RequestDetail>(`/requests/${id}/hand-over/`),
  issuePurchaseOrder: (id: string, supplier: string, terms: string) =>
    api.post<RequestDetail>(`/requests/${id}/purchase-order/`, { supplier, terms }),
  purchaseOrderPath: (id: string) => `/requests/${id}/purchase-order/`,
  routePreview: (request_type: string, department: string | null, amount: string) =>
    api.post<{ route: RoutePreview | null }>('/requests/route-preview/', { request_type, department, amount }),
  opsStatus: (id: string, status: Status, remarks: string) =>
    api.post<RequestDetail>(`/requests/${id}/ops/status/`, { status, remarks }),
  opsUpdate: (id: string, payload: Record<string, unknown>) => api.patch<RequestDetail>(`/requests/${id}/ops/`, payload),
}

export const approvalsApi = {
  pending: () => api.get<PendingApproval[]>('/approvals/'),
  history: (page: number) => api.get<Paginated<ApprovalHistoryItem>>('/approvals/history/', { page }),
  bulkApprove: (ids: string[], comments = '') =>
    api.post<{ approved: string[]; failed: { number: string; detail: string }[] }>('/approvals/bulk-approve/', { ids, comments }),
}
