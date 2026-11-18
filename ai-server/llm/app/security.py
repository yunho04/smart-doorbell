"""요청 인증 (SAD 6.1).

- Pi -> AI 서버      : X-Device-Key 헤더 (장치 키)
- Spring/Vision -> LLM: X-Internal-Token 헤더 (내부 토큰)

.env에 값이 비어 있으면 개발 모드로 보고 검사를 건너뛴다.
"""
import hmac
import logging

from fastapi import Header, HTTPException

from app.config import settings

log = logging.getLogger("ai-llm")

if not settings.DEVICE_KEYS:
    log.warning("DEVICE_KEYS 미설정: 장치 키 검사를 건너뜁니다 (개발 모드)")
if not settings.INTERNAL_TOKEN:
    log.warning("INTERNAL_TOKEN 미설정: 내부 토큰 검사를 건너뜁니다 (개발 모드)")


def verify_device_key(x_device_key: str | None = Header(None)) -> None:
    if not settings.DEVICE_KEYS:
        return
    if not x_device_key or not any(hmac.compare_digest(x_device_key, k) for k in settings.DEVICE_KEYS):
        raise HTTPException(401, detail="유효하지 않은 장치 키")


def verify_internal_token(x_internal_token: str | None = Header(None)) -> None:
    if not settings.INTERNAL_TOKEN:
        return
    if not x_internal_token or not hmac.compare_digest(x_internal_token, settings.INTERNAL_TOKEN):
        raise HTTPException(401, detail="유효하지 않은 내부 토큰")
