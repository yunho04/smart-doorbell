"""Groq API 클라이언트 (OpenAI 호환).

Groq는 OpenAI와 같은 형식의 API를 제공하므로 openai 라이브러리로 접속한다.
나중에 OpenAI·Gemini(OpenAI 호환 주소)로 바꿀 때도 .env의 주소·모델만 바꾸면 된다.
"""
import logging
from functools import lru_cache

from app.config import settings

log = logging.getLogger("ai-llm")


def groq_ready() -> bool:
    return bool(settings.GROQ_API_KEY)


@lru_cache(maxsize=1)
def get_client():
    from openai import OpenAI   # 키가 없을 때(mock)는 라이브러리를 불러오지 않는다
    return OpenAI(api_key=settings.GROQ_API_KEY, base_url=settings.GROQ_BASE_URL, max_retries=1)
