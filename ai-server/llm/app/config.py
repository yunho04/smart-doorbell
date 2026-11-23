"""환경 설정. 값은 .env 파일에서 읽어 온다."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _list(name: str) -> list[str]:
    return [v.strip() for v in os.getenv(name, "").split(",") if v.strip()]


class Settings:
    # ---------- STT·LLM 백엔드 ----------
    # groq: Groq API 사용 (GROQ_API_KEY 필요) / mock: 규칙 기반 가짜 응답 (키 없이 흐름 테스트)
    STT_BACKEND: str = os.getenv("STT_BACKEND", "mock")        # mock | groq
    LLM_BACKEND: str = os.getenv("LLM_BACKEND", "mock")        # mock | groq

    # Groq (OpenAI 호환 API). 키는 .env에만 넣고 GitHub에 올리지 않는다.
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

    # 최종 위험도 판단·요약 (finalize 때 1회) / 방문 목적 분류 (음성마다, 빨라야 함)
    LLM_MODEL: str = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
    LLM_FAST_MODEL: str = os.getenv("LLM_FAST_MODEL", "openai/gpt-oss-20b")
    LLM_REASONING_EFFORT: str = os.getenv("LLM_REASONING_EFFORT", "low")   # gpt-oss 전용: low | medium | high
    LLM_TIMEOUT_SEC: float = float(os.getenv("LLM_TIMEOUT_SEC", "10"))

    STT_MODEL: str = os.getenv("STT_MODEL", "whisper-large-v3-turbo")      # 정확도가 아쉬우면 whisper-large-v3
    STT_LANGUAGE: str = os.getenv("STT_LANGUAGE", "ko")
    STT_TIMEOUT_SEC: float = float(os.getenv("STT_TIMEOUT_SEC", "10"))

    # Spring 주소 (통합 당일에는 Mac의 실제 LAN IP 사용, localhost 금지)
    SPRING_BASE_URL: str = os.getenv("SPRING_BASE_URL", "http://localhost:8080").rstrip("/")
    SPRING_TIMEOUT_SEC: float = float(os.getenv("SPRING_TIMEOUT_SEC", "3"))

    # 중간 대사를 Spring /response로도 보낼지 (11-18 결정: Pi B가 /audio 응답으로 바로 재생 -> 기본 끔)
    # 켜면 Spring이 MQTT로도 Pi B에 보내서 두 번 재생될 수 있으므로 Pi B 쪽과 맞춘 뒤 켤 것
    SEND_RESPONSE_TO_SPRING: bool = os.getenv("SEND_RESPONSE_TO_SPRING", "false").lower() == "true"

    # Vision 서버 주소 (대표 사진 번호 전달용). 비우면 전달하지 않는다.
    VISION_BASE_URL: str = os.getenv("VISION_BASE_URL", "").rstrip("/")
    VISION_API_TOKEN: str = os.getenv("VISION_API_TOKEN", "")   # Vision이 토큰 검사를 켰을 때만
    VISION_TIMEOUT_SEC: float = float(os.getenv("VISION_TIMEOUT_SEC", "8"))
    VISION_KEEP_FRAMES: int = int(os.getenv("VISION_KEEP_FRAMES", "300"))  # Vision이 이벤트당 보관하는 최근 사진 수

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
