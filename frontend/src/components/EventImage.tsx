import { useState } from 'react'
import { resolveApiUrl } from '../api/client'
import { isInProgress } from '../utils/labels'

interface EventImageProps {
  url: string | null | undefined
  status: string | null | undefined
  alt: string
  variant: 'thumb' | 'full'
}

/**
 * 대표사진. 주소가 없거나 불러오지 못하면 깨진 이미지 대신 안내 문구를 보여 준다.
 * <img>는 same-site 요청에 세션 cookie를 함께 보낸다.
 */
export function EventImage({ url, status, alt, variant }: EventImageProps) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null)

  const hasImage = Boolean(url) && failedUrl !== url

  if (!hasImage) {
    const message = !url && isInProgress(status) ? '대표 이미지 분석 중' : '대표 이미지 없음'
    return (
      <div className={`event-image event-image-${variant} event-image-empty`}>
        <span>{message}</span>
      </div>
    )
  }

  return (
    <div className={`event-image event-image-${variant}`}>
      <img
        src={resolveApiUrl(url as string)}
        alt={alt}
        loading={variant === 'thumb' ? 'lazy' : undefined}
        onError={() => setFailedUrl(url as string)}
      />
    </div>
  )
}
