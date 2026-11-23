import type { EventStatus } from '../types/event'
import { isInProgress, STATUS_LABELS } from '../utils/labels'

export function StatusLabel({ status }: { status: string | null | undefined }) {
  const label = STATUS_LABELS[status as EventStatus] ?? '상태 알 수 없음'
  const tone = isInProgress(status) ? 'live' : status === 'FAILED' ? 'failed' : 'done'

  return (
    <span className={`status status-${tone}`}>
      <span className="status-dot" aria-hidden="true" />
      {label}
    </span>
  )
}
