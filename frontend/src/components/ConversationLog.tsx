import type { ConversationTurn } from '../types/event'

interface ConversationLogProps {
  turns: ConversationTurn[]
}

/**
 * 방문자와 AI가 주고받은 대화를 메신저 형태로 보여 준다.
 * 저장 시각은 실제 발화 시각이 아니므로 시간 대신 turnNo로 순서를 표시한다.
 */
export function ConversationLog({ turns }: ConversationLogProps) {
  const ordered = [...turns].sort((a, b) => (a.turnNo ?? 0) - (b.turnNo ?? 0))

  return (
    <ol className="chat">
      {ordered.map((turn, index) => {
        const heard = (turn.visitorText ?? '').trim() !== ''
        return (
          <li key={turn.turnNo ?? index} className="chat-turn">
            <p className="chat-turn-no">대화 {turn.turnNo ?? index + 1}</p>
            <div className="chat-message chat-visitor">
              <span className="chat-speaker">방문자</span>
              <p className={`chat-bubble${heard ? '' : ' chat-bubble-empty'}`}>
                {heard ? turn.visitorText : '발화 인식 안 됨'}
              </p>
            </div>
            <div className="chat-message chat-ai">
              <span className="chat-speaker">AI</span>
              <p className="chat-bubble">{turn.responseText || '(내용 없음)'}</p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
