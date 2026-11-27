import type { AccuracyLevel, EventStatus, RiskLevel } from '../types/event'

export const RISK_LABELS: Record<RiskLevel, string> = {
  LOW: '낮음',
  MEDIUM: '주의',
  HIGH: '위험',
}

export const STATUS_LABELS: Record<EventStatus, string> = {
  DETECTED: '방문 진행 중',
  ANALYZING: 'AI 분석 중',
  COMPLETED: '분석 완료',
  FAILED: '처리 실패',
}

export const ACCURACY_OPTIONS: { value: AccuracyLevel; label: string; hint: string }[] = [
  { value: 'HIGH', label: '상', hint: '정확했어요' },
  { value: 'MEDIUM', label: '중', hint: '애매했어요' },
  { value: 'LOW', label: '하', hint: '틀렸어요' },
]

export function isInProgress(status: string | null | undefined): boolean {
  return status === 'DETECTED' || status === 'ANALYZING'
}

export function isRiskLevel(value: unknown): value is RiskLevel {
  return value === 'LOW' || value === 'MEDIUM' || value === 'HIGH'
}

export function isAccuracyLevel(value: unknown): value is AccuracyLevel {
  return value === 'LOW' || value === 'MEDIUM' || value === 'HIGH'
}

/** 요약이 아직 없을 때 상태에 맞춰 보여 줄 문장 */
export function summaryPlaceholder(status: string | null | undefined): string {
  switch (status) {
    case 'DETECTED':
      return '방문자가 문 앞에 있습니다. 방문이 끝나면 요약이 표시됩니다.'
    case 'ANALYZING':
      return 'AI가 방문 상황을 분석하고 있습니다.'
    case 'FAILED':
      return '이 방문은 분석하지 못했습니다.'
    default:
      return '상황 요약이 없습니다.'
  }
}
