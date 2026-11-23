import { useEffect, useRef, useState } from 'react'
import { isAbortError } from '../api/client'

interface PollingOptions<T> {
  intervalMs: number
  /** false를 돌려주면 다음 호출을 예약하지 않는다. 생략하면 계속 반복한다. */
  shouldContinue?: (data: T | undefined, error: unknown) => boolean
}

interface PollingState<T> {
  data: T | undefined
  error: unknown
  loading: boolean
  /** 마지막으로 성공한 시각 */
  updatedAt: Date | null
  setData: (data: T) => void
}

/**
 * fetcher를 즉시 한 번 호출하고, 응답이 끝난 뒤 intervalMs마다 다시 호출한다.
 * 이전 요청이 끝나기 전에는 다음 요청을 보내지 않으며,
 * unmount 시 타이머와 진행 중인 요청을 모두 정리한다.
 * fetcher는 useCallback으로 고정해서 넘겨야 한다.
 */
export function usePolling<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  { intervalMs, shouldContinue }: PollingOptions<T>,
): PollingState<T> {
  const [data, setData] = useState<T | undefined>(undefined)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)

  const shouldContinueRef = useRef(shouldContinue)
  useEffect(() => {
    shouldContinueRef.current = shouldContinue
  })

  useEffect(() => {
    const controller = new AbortController()
    let timer: number | undefined
    let stopped = false

    const tick = async () => {
      let latest: T | undefined
      let failure: unknown = null

      try {
        latest = await fetcher(controller.signal)
        if (stopped) return
        setData(latest)
        setError(null)
        setUpdatedAt(new Date())
      } catch (caught) {
        if (stopped || isAbortError(caught)) return
        failure = caught
        setError(caught)
      }

      setLoading(false)

      const keepGoing = shouldContinueRef.current?.(latest, failure) ?? true
      if (!stopped && keepGoing) {
        timer = window.setTimeout(tick, intervalMs)
      }
    }

    void tick()

    return () => {
      stopped = true
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [fetcher, intervalMs])

  return { data, error, loading, updatedAt, setData }
}
