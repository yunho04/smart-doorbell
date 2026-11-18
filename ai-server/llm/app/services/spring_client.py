"""LLM 서버 -> Spring 호출 (명세서 MVP v1 3장, 5장).

- POST /api/v1/events/{eventId}/response : 중간 대사 전달 (Spring이 MQTT로 Pi B에 전달)
- POST /api/v1/events/{eventId}/result   : 최종 위험도·요약 전달 (Spring이 COMPLETED 처리)

실패해도 예외를 던지지 않고 False를 돌려준다 (AI 서버 처리를 막지 않음).
"""
import logging

import httpx

from app.config import settings
from app.schemas import SpringResponseRequest, SpringResultRequest

log = logging.getLogger("ai-llm")


def _post(path: str, payload: dict, event_id: int) -> bool:
    url = settings.SPRING_BASE_URL + path
    headers = {"X-Internal-Token": settings.INTERNAL_TOKEN} if settings.INTERNAL_TOKEN else {}
    for attempt in (1, 2):  # 일시 오류 대비 1회 재시도 (무한 재시도 X)
        try:
            r = httpx.post(url, json=payload, headers=headers, timeout=settings.SPRING_TIMEOUT_SEC)
            r.raise_for_status()
            log.info("Spring 전송 성공 %s eventId=%s status=%s", path, event_id, r.status_code)
            return True
        except httpx.HTTPError as e:
            log.warning("Spring 전송 실패(%d회차) %s eventId=%s: %s", attempt, path, event_id, e)
    return False


def send_response(event_id: int, body: SpringResponseRequest) -> bool:
    return _post(f"/api/v1/events/{event_id}/response", body.model_dump(by_alias=True), event_id)


def send_result(event_id: int, body: SpringResultRequest) -> bool:
    return _post(f"/api/v1/events/{event_id}/result",
                 body.model_dump(by_alias=True, mode="json"), event_id)
