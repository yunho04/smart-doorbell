"""LLM 서버 -> Vision 서버 : 대표 사진 번호 전달.

11-18 결정: LLM이 finalize 때 대표 사진 frame_no를 골라 Vision에 보내면,
Vision이 그 사진 원본을 Spring POST /api/v1/events/{id}/image 로 올린다.

Vision API (Vision README):
  POST {VISION_BASE_URL}/vision/events/{event_id}/representative
  body {"frame_no": 12}
  200 업로드 성공 / 404 사진 없음 / 502 Spring 실패 / 503 Vision에 SPRING_URL 미설정
"""
import logging

import httpx

from app.config import settings

log = logging.getLogger("ai-llm")


def send_representative(event_id: int, frame_no: int) -> bool:
    """실패해도 예외를 던지지 않는다 (대표 사진이 없어도 /result는 이미 전송됨)."""
    if not settings.VISION_BASE_URL:
        log.info("VISION_BASE_URL 미설정: 대표 사진 전달 생략 eventId=%s frame=%s", event_id, frame_no)
        return False

    url = f"{settings.VISION_BASE_URL}/vision/events/{event_id}/representative"
    headers = {"Authorization": f"Bearer {settings.VISION_API_TOKEN}"} if settings.VISION_API_TOKEN else {}
    try:
        r = httpx.post(url, json={"frame_no": frame_no}, headers=headers, timeout=settings.VISION_TIMEOUT_SEC)
        r.raise_for_status()
        log.info("대표 사진 전달 성공 eventId=%s frame=%s -> %s", event_id, frame_no, r.text[:200])
        return True
    except httpx.HTTPStatusError as e:
        log.warning("대표 사진 전달 실패 eventId=%s frame=%s: Vision %s %s",
                    event_id, frame_no, e.response.status_code, e.response.text[:200])
    except httpx.HTTPError as e:
        log.warning("대표 사진 전달 실패 eventId=%s frame=%s: %s", event_id, frame_no, e)
    return False
