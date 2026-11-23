export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH'

export type EventStatus = 'DETECTED' | 'ANALYZING' | 'COMPLETED' | 'FAILED'

export type AccuracyLevel = 'HIGH' | 'MEDIUM' | 'LOW'

export interface AuthResponse {
  authenticated: boolean
}

/** GET /api/v1/events 의 항목 */
export interface EventSummary {
  eventId: number
  status: EventStatus
  startedAt: string | null
  endedAt: string | null
  riskLevel: RiskLevel | null
  summary: string | null
  representativeImageUrl: string | null
  feedback: AccuracyLevel | null
}

/** AI가 방문자에게 응대한 기록 한 건 */
export interface EventResponse {
  responseId: number
  responseCode: string | null
  responseText: string | null
  createdAt: string | null
}

/** GET /api/v1/events/{eventId} */
export interface EventDetail extends EventSummary {
  responses: EventResponse[] | null
}

/** POST /api/v1/events/{eventId}/feedback */
export interface FeedbackRequest {
  accuracyLevel: AccuracyLevel
}
