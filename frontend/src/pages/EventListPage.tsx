import { useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { describeError } from '../api/client'
import { fetchEvents } from '../api/events'
import { EventImage } from '../components/EventImage'
import { RiskBadge } from '../components/RiskBadge'
import { StatusLabel } from '../components/StatusLabel'
import { usePolling } from '../hooks/usePolling'
import type { EventSummary } from '../types/event'
import {
  dayKey,
  formatClock,
  formatDayHeading,
  formatDuration,
  formatTime,
  parseDate,
} from '../utils/format'
import { isInProgress, summaryPlaceholder } from '../utils/labels'

const POLL_INTERVAL_MS = 3000

interface DayGroup {
  key: string
  heading: string
  events: EventSummary[]
}

/** 최근 Event가 위로 오도록 정렬한 뒤 날짜별로 묶는다. */
function groupByDay(events: EventSummary[]): DayGroup[] {
  const sorted = [...events].sort((a, b) => {
    const timeA = parseDate(a.startedAt)?.getTime() ?? 0
    const timeB = parseDate(b.startedAt)?.getTime() ?? 0
    return timeB - timeA || b.eventId - a.eventId
  })

  const groups: DayGroup[] = []
  for (const event of sorted) {
    const key = dayKey(event.startedAt)
    const last = groups[groups.length - 1]
    if (last && last.key === key) {
      last.events.push(event)
    } else {
      groups.push({ key, heading: formatDayHeading(event.startedAt), events: [event] })
    }
  }
  return groups
}

export function EventListPage() {
  const fetcher = useCallback((signal: AbortSignal) => fetchEvents(signal), [])
  const { data, error, loading, updatedAt } = usePolling(fetcher, {
    intervalMs: POLL_INTERVAL_MS,
  })

  const groups = useMemo(() => groupByDay(data ?? []), [data])
  const total = data?.length ?? 0

  return (
    <>
      <div className="page-head">
        <h1 className="page-title">방문 이벤트 기록</h1>
        {data && (
          <p className="page-meta">
            총 {total}건, 3초마다 새로 확인합니다
            {updatedAt && <> (마지막 확인 {formatTime(updatedAt.toISOString())})</>}
          </p>
        )}
      </div>

      {error !== null && data && (
        <p className="notice notice-error" role="alert">
          {describeError(error, '이벤트 목록을 새로 불러오지 못했습니다.')} 마지막으로 받은 기록을
          보여 주고 있으며, 연결되면 자동으로 갱신됩니다.
        </p>
      )}

      {loading && !data && (
        <p className="state-text" role="status">
          이벤트 정보를 불러오는 중...
        </p>
      )}

      {error !== null && !data && !loading && (
        <div className="state-block" role="alert">
          <p className="state-title">
            {describeError(error, '이벤트 목록을 불러오지 못했습니다.')}
          </p>
          <p className="state-text">3초마다 다시 시도하고 있습니다.</p>
        </div>
      )}

      {data && total === 0 && (
        <div className="state-block">
          <p className="state-title">아직 방문 기록이 없습니다.</p>
          <p className="state-text">누군가 문 앞에 오면 여기에 바로 표시됩니다.</p>
        </div>
      )}

      {groups.map((group) => (
        <section key={group.key} className="day">
          <h2 className="day-heading">{group.heading}</h2>
          <ul className="event-list">
            {group.events.map((event) => (
              <EventRow key={event.eventId} event={event} />
            ))}
          </ul>
        </section>
      ))}
    </>
  )
}

function EventRow({ event }: { event: EventSummary }) {
  const start = formatTime(event.startedAt)
  const end = formatTime(event.endedAt)
  const duration = formatDuration(event.startedAt, event.endedAt)
  const live = isInProgress(event.status)

  return (
    <li>
      <Link to={`/events/${event.eventId}`} className={`event-row${live ? ' event-row-live' : ''}`}>
        <div className="event-clock">{formatClock(event.startedAt) ?? '--:--'}</div>

        <EventImage
          url={event.representativeImageUrl}
          status={event.status}
          alt={`이벤트 ${event.eventId} 대표사진`}
          variant="thumb"
        />

        <div className="event-body">
          <p className={`event-summary${event.summary ? '' : ' event-summary-empty'}`}>
            {event.summary ?? summaryPlaceholder(event.status)}
          </p>
          <dl className="event-facts">
            <div>
              <dt>이벤트</dt>
              <dd>#{event.eventId}</dd>
            </div>
            <div>
              <dt>시작</dt>
              <dd>{start ?? '기록 없음'}</dd>
            </div>
            <div>
              <dt>종료</dt>
              <dd>
                {end ?? (live ? '진행 중' : '기록 없음')}
                {duration && <span className="event-duration"> ({duration})</span>}
              </dd>
            </div>
          </dl>
        </div>

        <div className="event-tags">
          <RiskBadge level={event.riskLevel} />
          <StatusLabel status={event.status} />
        </div>
      </Link>
    </li>
  )
}
