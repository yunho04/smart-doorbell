import type { AuthResponse } from '../types/event'
import { request } from './client'

export function login(password: string): Promise<AuthResponse | undefined> {
  return request<AuthResponse | undefined>('/api/v1/auth/login', {
    method: 'POST',
    body: { password },
    skipUnauthorizedHandler: true,
  })
}

export function checkAuth(signal?: AbortSignal): Promise<AuthResponse | undefined> {
  return request<AuthResponse | undefined>('/api/v1/auth/check', {
    signal,
    skipUnauthorizedHandler: true,
  })
}

export function logout(): Promise<void> {
  return request<void>('/api/v1/auth/logout', {
    method: 'POST',
    skipUnauthorizedHandler: true,
  })
}
