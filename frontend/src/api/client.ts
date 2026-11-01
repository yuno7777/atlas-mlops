import type { JsonObject } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api/v1'
const TOKEN_KEY = 'atlas.token'
const USER_KEY = 'atlas.user'

export class ApiError extends Error {
  status: number
  code: string
  details: unknown
  requestId: string | null

  constructor(
    message: string,
    options: { status?: number; code?: string; details?: unknown; requestId?: string | null } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = options.status ?? 0
    this.code = options.code ?? 'request_failed'
    this.details = options.details
    this.requestId = options.requestId ?? null
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setSession(token: string, user: unknown) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function readStoredUser<T>(): T | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

type QueryValue = string | number | boolean | null | undefined
export type QueryParams = Record<string, QueryValue>

function buildUrl(path: string, query?: QueryParams): string {
  const url = `${API_BASE}${path}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }
  const suffix = params.toString()
  return suffix ? `${url}?${suffix}` : url
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    // ignore non-JSON responses
  }
  const envelope = payload as
    | {
        error?: { code?: string; message?: string; details?: unknown; request_id?: string }
        detail?: unknown
      }
    | null
  if (envelope?.error) {
    return new ApiError(envelope.error.message ?? `Request failed (${response.status})`, {
      status: response.status,
      code: envelope.error.code,
      details: envelope.error.details,
      requestId: envelope.error.request_id,
    })
  }
  if (Array.isArray(envelope?.detail)) {
    const first = envelope.detail[0] as { msg?: string; loc?: unknown[] } | undefined
    return new ApiError(first?.msg ?? 'The request was rejected.', {
      status: response.status,
      code: 'validation_error',
      details: envelope.detail,
    })
  }
  if (typeof envelope?.detail === 'string') {
    return new ApiError(envelope.detail, { status: response.status })
  }
  return new ApiError(`Request failed (${response.status}).`, { status: response.status })
}

async function request<T>(
  method: string,
  path: string,
  options: {
    query?: QueryParams
    body?: unknown
    form?: FormData
    signal?: AbortSignal
  } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined
  if (options.form) {
    body = options.form
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method,
      headers,
      body,
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('Cannot reach the Atlas API. Check that the backend is running.')
  }

  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) {
      window.dispatchEvent(new CustomEvent('atlas:unauthorized'))
    }
    throw await parseError(response)
  }
  if (response.status === 204) return undefined as T
  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) return (await response.text()) as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string, query?: QueryParams, signal?: AbortSignal) =>
    request<T>('GET', path, { query, signal }),
  post: <T>(path: string, body?: unknown, query?: QueryParams) =>
    request<T>('POST', path, { body, query }),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, { body }),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, { body }),
  delete: <T>(path: string) => request<T>('DELETE', path),
  upload: <T>(path: string, form: FormData) => request<T>('POST', path, { form }),
}

function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (utf8?.[1]) return decodeURIComponent(utf8[1])
  const plain = /filename="?([^";]+)"?/i.exec(header)
  return plain?.[1] ?? fallback
}

export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const token = getToken()
  const response = await fetch(buildUrl(path), {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  })
  if (!response.ok) throw await parseError(response)
  const blob = await response.blob()
  const filename = filenameFromDisposition(response.headers.get('content-disposition'), fallbackName)
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Something went wrong.'
}

export function errorDetails(error: unknown): string[] {
  if (!(error instanceof ApiError) || !Array.isArray(error.details)) return []
  return error.details.map((item) => {
    const entry = item as { loc?: unknown[]; msg?: string }
    const location = Array.isArray(entry.loc)
      ? entry.loc.filter((part) => part !== 'body').join('.')
      : ''
    return location ? `${location}: ${entry.msg ?? 'Invalid value'}` : entry.msg ?? 'Invalid value'
  })
}

export function detailJson(details: JsonObject | null | undefined): string {
  return JSON.stringify(details ?? {}, null, 2)
}
