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

/** 방문자 발화 한 번과 그에 대한 AI 응답 한 번 */
export interface ConversationTurn {
  turnNo: number | null
  visitorText: string | null
  purpose: string | null
  responseCode: string | null
  responseText: string | null
}

/** GET /api/v1/events/{eventId} (Backend EventDetailResponse) */
export interface EventDetail extends EventSummary {
  deviceId?: number | null
  responseCode?: string | null
  responseText?: string | null
  responses: EventResponse[] | null
  /** 최종 방문 목적 */
  purpose?: string | null
  /** 전체 대화 요약 */
  conversationSummary?: string | null
  /** 대화 기록. 예전 이벤트는 비어 있다. */
  conversation?: ConversationTurn[] | null
}

/** POST /api/v1/events/{eventId}/feedback */
export interface FeedbackRequest {
  accuracyLevel: AccuracyLevel
}
