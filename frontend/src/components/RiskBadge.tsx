import { isRiskLevel, RISK_LABELS } from '../utils/labels'

interface RiskBadgeProps {
  level: string | null | undefined
  size?: 'default' | 'large'
}

export function RiskBadge({ level, size = 'default' }: RiskBadgeProps) {
  const sizeClass = size === 'large' ? ' risk-badge-large' : ''

  if (!isRiskLevel(level)) {
    return <span className={`risk-badge risk-none${sizeClass}`}>위험도 판단 전</span>
  }

  return (
    <span className={`risk-badge risk-${level.toLowerCase()}${sizeClass}`}>
      <span className="risk-dot" aria-hidden="true" />
      <span className="visually-hidden">위험도 </span>
      {RISK_LABELS[level]}
    </span>
  )
}
