"""환경 설정. 값은 .env 파일에서 읽어 온다."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _list(name: str) -> list[str]:
    return [v.strip() for v in os.getenv(name, "").split(",") if v.strip()]


class Settings:
    # 각 기능을 실제 구현으로 바꿀 때 mock -> 실제 이름으로 변경
    STT_BACKEND: str = os.getenv("STT_BACKEND", "mock")        # mock | whisper
    LLM_BACKEND: str = os.getenv("LLM_BACKEND", "mock")        # mock | openai | anthropic | gemini
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "mock-llm")

    # Spring 주소 (통합 당일에는 Mac의 실제 LAN IP 사용, localhost 금지)
    SPRING_BASE_URL: str = os.getenv("SPRING_BASE_URL", "http://localhost:8080").rstrip("/")
    SPRING_TIMEOUT_SEC: float = float(os.getenv("SPRING_TIMEOUT_SEC", "3"))

    # 인증: MVP v1에서는 사용하지 않음 (비워 두면 검사 생략). 후속 단계에서 켠다.
    DEVICE_KEYS: list[str] = _list("DEVICE_KEYS")
    INTERNAL_TOKEN: str = os.getenv("INTERNAL_TOKEN", "")

    # 이벤트별 Vision·STT 결과 보관 시간
    EVENT_CACHE_TTL_SEC: int = int(os.getenv("EVENT_CACHE_TTL_SEC", "3600"))

    # 방문 목적 분류 신뢰도가 이 값보다 낮으면 UNKNOWN 처리 (NFR-03)
    PURPOSE_CONF_THRESHOLD: float = float(os.getenv("PURPOSE_CONF_THRESHOLD", "0.6"))
    MAX_TURNS: int = int(os.getenv("MAX_TURNS", "3"))
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "5"))

    AUDIO_DIR: Path = BASE_DIR / os.getenv("AUDIO_DIR", "storage/audio")
    CASES_PATH: Path = BASE_DIR / os.getenv("CASES_PATH", "data/cases.json")
    TEMPLATES_PATH: Path = BASE_DIR / "data/reply_templates.json"


settings = Settings()
settings.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
