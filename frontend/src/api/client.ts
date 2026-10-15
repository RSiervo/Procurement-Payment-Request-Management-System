/** Thin fetch wrapper: same-origin session cookie, CSRF header, uniform errors. */

export class ApiError extends Error {
  status: number
  errors: Record<string, string[]>

  constructor(status: number, detail: string, errors: Record<string, string[]> = {}) {
    super(detail)
    this.status = status
    this.errors = errors
  }

  /** First message for a field, if the server reported one. */
  field(name: string): string | undefined {
    const value = this.errors[name]
    return Array.isArray(value) ? value[0] : typeof value === 'string' ? value : undefined
  }
}

type Query = Record<string, string | number | boolean | null | undefined>

let csrfToken: string | null = null
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

async function ensureCsrf(): Promise<string> {
  csrfToken = readCookie('csrftoken') ?? csrfToken
  if (!csrfToken) {
    const response = await fetch('/api/auth/csrf/', { credentials: 'same-origin' })
    csrfToken = (await response.json()).csrfToken
  }
  return csrfToken as string
}

export function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  }
  const suffix = params.toString()
  return `/api${path}${suffix ? `?${suffix}` : ''}`
}

async function toError(response: Response): Promise<ApiError> {
  let detail = `Request failed (${response.status}).`
  let errors: Record<string, string[]> = {}
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') detail = body.detail
    if (body.errors && typeof body.errors === 'object') errors = body.errors
  } catch {
    if (response.status >= 500) detail = 'The server ran into a problem. Please try again.'
  }
  return new ApiError(response.status, detail, errors)
}

async function send(method: string, path: string, options: { query?: Query; body?: unknown } = {}): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  let body: BodyInit | undefined
  if (options.body instanceof FormData) {
    body = options.body
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }
  if (method !== 'GET') headers['X-CSRFToken'] = await ensureCsrf()

  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), { method, headers, body, credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, 'Could not reach the server. Check your connection and try again.')
  }
  if (!response.ok) {
    const error = await toError(response)
    // DRF answers 403 for both "not signed in" and "not allowed"; only the former mentions credentials.
    if (response.status === 403 && /credentials/i.test(error.message) && !path.startsWith('/auth/')) {
      onUnauthorized?.()
    }
    if (response.status === 403 && /csrf/i.test(error.message)) csrfToken = null
    throw error
  }
  return response
}

async function json<T>(method: string, path: string, options?: { query?: Query; body?: unknown }): Promise<T> {
  const response = await send(method, path, options)
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

export const api = {
  get: <T>(path: string, query?: Query) => json<T>('GET', path, { query }),
  post: <T>(path: string, body?: unknown) => json<T>('POST', path, { body: body ?? {} }),
  patch: <T>(path: string, body: unknown) => json<T>('PATCH', path, { body }),
  put: <T>(path: string, body: unknown) => json<T>('PUT', path, { body }),
  delete: (path: string) => json<void>('DELETE', path),
  blob: async (path: string, query?: Query) => (await send('GET', path, { query })).blob(),
}

/** Fetch a file with the session cookie and hand it to the browser as a download. */
export async function downloadFile(path: string, filename: string, query?: Query) {
  const url = URL.createObjectURL(await api.blob(path, query))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

/** Open a file (PDF or image) in a new tab. The tab is opened first so pop-up blockers allow it. */
export async function openFile(path: string, query?: Query) {
  const tab = window.open('', '_blank')
  try {
    const url = URL.createObjectURL(await api.blob(path, query))
    if (tab) tab.location.href = url
    else window.location.href = url
    setTimeout(() => URL.revokeObjectURL(url), 5 * 60_000)
  } catch (error) {
    tab?.close()
    throw error
  }
}

/** Load a PDF into a hidden frame and open the browser's print dialog. */
export async function printFile(path: string) {
  const url = URL.createObjectURL(await api.blob(path))
  const frame = document.createElement('iframe')
  frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0'
  frame.src = url
  frame.onload = () => {
    try {
      frame.contentWindow?.focus()
      frame.contentWindow?.print()
    } catch {
      window.open(url, '_blank') // some mobile browsers cannot print from a frame
    }
  }
  document.body.appendChild(frame)
  setTimeout(() => {
    frame.remove()
    URL.revokeObjectURL(url)
  }, 5 * 60_000)
}
