import type { AccuracyLevel, EventDetail, EventSummary, FeedbackRequest } from '../types/event'
import { request } from './client'

export async function fetchEvents(signal?: AbortSignal): Promise<EventSummary[]> {
  const data = await request<EventSummary[] | undefined>('/api/v1/events', { signal })
  return Array.isArray(data) ? data : []
}

export function fetchEvent(eventId: string | number, signal?: AbortSignal): Promise<EventDetail> {
  return request<EventDetail>(`/api/v1/events/${encodeURIComponent(eventId)}`, { signal })
}

/** Backend 응답 형식이 확정되지 않았으므로 응답 본문은 그대로 돌려준다. */
export function sendFeedback(
  eventId: string | number,
  accuracyLevel: AccuracyLevel,
): Promise<unknown> {
  const body: FeedbackRequest = { accuracyLevel }
  return request<unknown>(`/api/v1/events/${encodeURIComponent(eventId)}/feedback`, {
    method: 'POST',
    body,
  })
}
