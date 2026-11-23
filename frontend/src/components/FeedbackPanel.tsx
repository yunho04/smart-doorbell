import type { AccuracyLevel } from '../types/event'
import { ACCURACY_OPTIONS } from '../utils/labels'

export interface FeedbackMessage {
  tone: 'success' | 'error'
  text: string
}

interface FeedbackPanelProps {
  current: AccuracyLevel | null
  /** 위험도 판단이 아직 없으면 평가할 수 없다. */
  enabled: boolean
  saving: AccuracyLevel | null
  message: FeedbackMessage | null
  onSelect: (level: AccuracyLevel) => void
}

export function FeedbackPanel({ current, enabled, saving, message, onSelect }: FeedbackPanelProps) {
  return (
    <section className="section feedback" aria-labelledby="feedback-title">
      <h2 id="feedback-title" className="section-title">
        AI의 위험도 판단이 정확했나요?
      </h2>

      <div className="feedback-options" role="group" aria-labelledby="feedback-title">
        {ACCURACY_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            className="feedback-option"
            aria-pressed={current === option.value}
            disabled={!enabled || saving !== null}
            onClick={() => onSelect(option.value)}
          >
            <span className="feedback-grade">{option.label}</span>
            <span className="feedback-hint">
              {saving === option.value ? '저장 중...' : option.hint}
            </span>
          </button>
        ))}
      </div>

      {!enabled && (
        <p className="feedback-note">AI가 위험도를 판단한 뒤에 평가할 수 있습니다.</p>
      )}
      {enabled && !message && (
        <p className="feedback-note">
          {current ? '다른 값을 누르면 평가가 바뀝니다.' : '평가는 이후 AI 판단에 반영됩니다.'}
        </p>
      )}
      {message && (
        <p
          className={`feedback-note feedback-note-${message.tone}`}
          role={message.tone === 'error' ? 'alert' : 'status'}
        >
          {message.text}
        </p>
      )}
    </section>
  )
}
