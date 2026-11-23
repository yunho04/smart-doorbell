const pad = (value: number) => String(value).padStart(2, '0')

/** Backend의 LocalDateTime 문자열을 Date로 바꾼다. 잘못된 값이면 null. */
export function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/** 15:20:13 */
export function formatTime(value: string | null | undefined): string | null {
  const date = parseDate(value)
  if (!date) return null
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

/** 15:20 */
export function formatClock(value: string | null | undefined): string | null {
  const date = parseDate(value)
  if (!date) return null
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const dateFormatter = new Intl.DateTimeFormat('ko-KR', {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  weekday: 'long',
})

/** 2026년 11월 24일 화요일 */
export function formatDate(value: string | null | undefined): string | null {
  const date = parseDate(value)
  return date ? dateFormatter.format(date) : null
}

/** 2026년 11월 24일 화요일 15:20:13 */
export function formatDateTime(value: string | null | undefined): string | null {
  const date = formatDate(value)
  const time = formatTime(value)
  return date && time ? `${date} ${time}` : null
}

/** 같은 날짜끼리 묶기 위한 키 */
export function dayKey(value: string | null | undefined): string {
  const date = parseDate(value)
  if (!date) return 'unknown'
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** 목록의 날짜 제목. 오늘과 어제는 말로 풀어 쓴다. */
export function formatDayHeading(value: string | null | undefined): string {
  const date = parseDate(value)
  if (!date) return '시간 정보 없음'

  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const diffDays = Math.round((startOfDay(new Date()) - startOfDay(date)) / 86_400_000)
  const label = dateFormatter.format(date)

  if (diffDays === 0) return `오늘, ${label}`
  if (diffDays === 1) return `어제, ${label}`
  return label
}

/** 52초 / 1분 5초 / 1시간 2분 */
export function formatDuration(
  startedAt: string | null | undefined,
  endedAt: string | null | undefined,
): string | null {
  const start = parseDate(startedAt)
  const end = parseDate(endedAt)
  if (!start || !end) return null

  const totalSeconds = Math.round((end.getTime() - start.getTime()) / 1000)
  if (totalSeconds < 0) return null

  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  if (hours > 0) return `${hours}시간 ${minutes}분`
  if (minutes > 0) return seconds > 0 ? `${minutes}분 ${seconds}초` : `${minutes}분`
  return `${seconds}초`
}
