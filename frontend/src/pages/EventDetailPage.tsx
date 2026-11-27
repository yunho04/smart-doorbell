import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, describeError } from '../api/client'
import { fetchEvent, sendFeedback } from '../api/events'
import { ConversationLog } from '../components/ConversationLog'
import { EventImage } from '../components/EventImage'
import { FeedbackPanel, type FeedbackMessage } from '../components/FeedbackPanel'
import { RiskBadge } from '../components/RiskBadge'
import { StatusLabel } from '../components/StatusLabel'
import { usePolling } from '../hooks/usePolling'
import type { AccuracyLevel, EventDetail } from '../types/event'
import { formatDateTime, formatDuration, formatTime } from '../utils/format'
import { isAccuracyLevel, isInProgress, isRiskLevel, summaryPlaceholder } from '../utils/labels'

const POLL_INTERVAL_MS = 3000

export function EventDetailPage() {
  const { eventId } = useParams()
  if (!eventId) return null
  // eventId가 바뀌면 화면 상태를 처음부터 다시 만든다.
  return <EventDetailView key={eventId} eventId={eventId} />
}

/** feedback 응답 본문에서 저장된 값을 찾는다. 형식을 알 수 없으면 null. */
function readSavedFeedback(response: unknown): AccuracyLevel | null {
  if (typeof response !== 'object' || response === null) return null
  const body = response as Record<string, unknown>
  if (isAccuracyLevel(body.feedback)) return body.feedback
  if (isAccuracyLevel(body.accuracyLevel)) return body.accuracyLevel
  return null
}

function EventDetailView({ eventId }: { eventId: string }) {
  const fetcher = useCallback((signal: AbortSignal) => fetchEvent(eventId, signal), [eventId])

  const {
    data: event,
    error,
    loading,
    setData,
  } = usePolling<EventDetail>(fetcher, {
    intervalMs: POLL_INTERVAL_MS,
    // 진행 중인 Event만 계속 확인한다. 완료/실패했거나 없는 Event면 멈춘다.
    shouldContinue: (latest, failure) => {
      if (failure) return !(failure instanceof ApiError && failure.status === 404)
      return isInProgress(latest?.status)
    },
  })

  const [saving, setSaving] = useState<AccuracyLevel | null>(null)
  const [message, setMessage] = useState<FeedbackMessage | null>(null)

  const handleFeedback = async (level: AccuracyLevel) => {
    if (!event) return
    setSaving(level)
    setMessage(null)

    try {
      const response = await sendFeedback(eventId, level)

      // Backend가 저장한 값을 화면에 반영한다.
      // 응답에 값이 없으면 상세를 다시 조회하고, 그것도 실패하면 보낸 값을 쓴다.
      const saved = readSavedFeedback(response)
      if (saved) {
        setData({ ...event, feedback: saved })
      } else {
        try {
          setData(await fetchEvent(eventId))
        } catch {
          setData({ ...event, feedback: level })
        }
      }
      setMessage({ tone: 'success', text: '피드백이 반영되었습니다.' })
    } catch (caught) {
      setMessage({
        tone: 'error',
        text: describeError(caught, '피드백을 저장하지 못했습니다. 다시 시도하세요.'),
      })
    } finally {
      setSaving(null)
    }
  }

  const backLink = (
    <Link to="/events" className="back-link">
      <span aria-hidden="true">‹</span> 방문 이벤트 기록
    </Link>
  )

  if (!event) {
    const notFound = error instanceof ApiError && error.status === 404
    return (
      <>
        {backLink}
        {loading && (
          <p className="state-text" role="status">
            이벤트 정보를 불러오는 중...
          </p>
        )}
        {!loading && error !== null && (
          <div className="state-block" role="alert">
            <p className="state-title">
              {notFound
                ? `이벤트 #${eventId}을(를) 찾을 수 없습니다.`
                : describeError(error, '이벤트 정보를 불러오지 못했습니다.')}
            </p>
            <p className="state-text">
              {notFound ? '목록에서 다른 이벤트를 선택하세요.' : '3초마다 다시 시도하고 있습니다.'}
            </p>
          </div>
        )}
      </>
    )
  }

  const live = isInProgress(event.status)
  const responses = Array.isArray(event.responses) ? event.responses : []
  // conversation이 없는 예전 이벤트는 responses 기반 표시를 유지한다.
  const conversation = Array.isArray(event.conversation) ? event.conversation : []
  const purpose = event.purpose?.trim() || null
  const conversationSummary = event.conversationSummary?.trim() || null
  const duration = formatDuration(event.startedAt, event.endedAt)

  return (
    <>
      {backLink}

      {error !== null && (
        <p className="notice notice-error" role="alert">
          {describeError(error, '최신 정보를 불러오지 못했습니다.')} 마지막으로 받은 내용을 보여
          주고 있습니다.
        </p>
      )}

      <article className="detail">
        <figure className="monitor">
          <EventImage
            url={event.representativeImageUrl}
            status={event.status}
            alt={`이벤트 ${event.eventId} 대표사진`}
            variant="full"
          />
          <figcaption className="monitor-caption">
            <span>이벤트 #{event.eventId}</span>
            <span>{formatTime(event.startedAt) ?? '시간 기록 없음'}</span>
          </figcaption>
        </figure>

        <div className="detail-body">
          <div className="detail-tags">
            <RiskBadge level={event.riskLevel} size="large" />
            <StatusLabel status={event.status} />
          </div>

          <h1 className={`detail-summary${event.summary ? '' : ' detail-summary-empty'}`}>
            {event.summary ?? summaryPlaceholder(event.status)}
          </h1>

          <dl className="detail-facts">
            <div>
              <dt>이벤트 ID</dt>
              <dd>{event.eventId}</dd>
            </div>
            <div>
              <dt>시작시간</dt>
              <dd>{formatDateTime(event.startedAt) ?? '기록 없음'}</dd>
            </div>
            <div>
              <dt>종료시간</dt>
              <dd>
                {formatDateTime(event.endedAt) ?? (live ? '아직 진행 중' : '기록 없음')}
                {duration && <span className="event-duration"> ({duration})</span>}
              </dd>
            </div>
            {purpose && (
              <div>
                <dt>방문 목적</dt>
                <dd>{purpose}</dd>
              </div>
            )}
            {conversationSummary && (
              <div>
                <dt>대화 요약</dt>
                <dd>{conversationSummary}</dd>
              </div>
            )}
          </dl>

          <section className="section" aria-labelledby="responses-title">
            <h2 id="responses-title" className="section-title">
              {conversation.length > 0 ? '대화 기록' : 'AI 응대 기록'}
            </h2>
            {conversation.length > 0 ? (
              <ConversationLog turns={conversation} />
            ) : responses.length === 0 ? (
              <p className="section-empty">응대 기록 없음</p>
            ) : (
              <ol className="responses">
                {responses.map((response, index) => (
                  <li key={response.responseId ?? index} className="response">
                    <time className="response-time">
                      {formatTime(response.createdAt) ?? '--:--:--'}
                    </time>
                    <p className="response-text">{response.responseText ?? '(내용 없음)'}</p>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <FeedbackPanel
            current={isAccuracyLevel(event.feedback) ? event.feedback : null}
            enabled={isRiskLevel(event.riskLevel)}
            saving={saving}
            message={message}
            onSelect={handleFeedback}
          />
        </div>
      </article>
    </>
  )
}
