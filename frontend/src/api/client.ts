const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

export type ApiErrorKind = 'network' | 'http' | 'parse'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null

  constructor(kind: ApiErrorKind, status: number | null, message: string) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

/** 화면에 그대로 보여 줄 수 있는 오류 문구로 바꾼다. */
export function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.kind === 'network') {
    return '서버에 연결할 수 없습니다.'
  }
  return fallback
}

/** Backend가 내려준 상대 경로(/api/...)를 실제 요청 주소로 바꾼다. */
export function resolveApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path
  return `${API_BASE_URL}${path.startsWith('/') ? '' : '/'}${path}`
}

let unauthorizedHandler: (() => void) | null = null

/** 세션 만료(401) 시 호출할 함수를 등록한다. AuthProvider가 사용한다. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  signal?: AbortSignal
  /** true면 401을 세션 만료로 취급하지 않는다. (로그인 요청용) */
  skipUnauthorizedHandler?: boolean
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal, skipUnauthorizedHandler = false } = options

  let response: Response
  try {
    response = await fetch(resolveApiUrl(path), {
      method,
      // Session Cookie 인증: 모든 요청에 cookie를 포함한다.
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    })
  } catch (error) {
    if (isAbortError(error)) throw error
    console.error(`[api] ${method} ${path} 연결 실패`, error)
    throw new ApiError('network', null, '서버에 연결할 수 없습니다.')
  }

  if (!response.ok) {
    console.error(`[api] ${method} ${path} → ${response.status}`)
    if (response.status === 401 && !skipUnauthorizedHandler) {
      unauthorizedHandler?.()
    }
    throw new ApiError('http', response.status, `요청이 실패했습니다. (${response.status})`)
  }

  const text = await response.text()
  if (text.trim() === '') return undefined as T

  try {
    return JSON.parse(text) as T
  } catch (error) {
    console.error(`[api] ${method} ${path} 응답을 해석할 수 없습니다.`, error)
    throw new ApiError('parse', response.status, '서버 응답을 해석할 수 없습니다.')
  }
}
