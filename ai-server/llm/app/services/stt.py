"""STT: 음성 파일 -> 텍스트.

- GroqSTT : Groq Whisper (whisper-large-v3-turbo). STT_BACKEND=groq + GROQ_API_KEY
- MockSTT : 파일 이름으로 문장을 정하는 가짜 STT (키 없이 흐름 테스트)

어떤 경우에도 예외를 던지지 않고 ("", 0.0)을 돌려준다
-> 방문 목적 UNKNOWN -> ASK_AGAIN_01 (다시 말씀해 주세요)로 자연스럽게 이어진다.
"""
import logging
import math
from pathlib import Path

from app.config import settings
from app.services.groq_client import get_client, groq_ready

log = logging.getLogger("ai-llm")

# Whisper가 무음·잡음에서 지어내는 대표 문장 (유튜브 자막 학습 영향). 이런 결과는 버린다.
HALLUCINATIONS = (
    "시청해 주셔서 감사합니다", "시청해주셔서 감사합니다", "구독과 좋아요", "구독 좋아요",
    "좋아요와 구독", "MBC 뉴스", "KBS 뉴스", "SBS 뉴스", "자막 제공", "자막은", "다음 영상에서",
    "감사합니다.", "Thank you", "thank you for watching",
)
NO_SPEECH_THRESHOLD = 0.6   # 세그먼트의 '말 없음' 확률이 이보다 높으면 버림


def clean_transcript(text: str, no_speech_prob: float = 0.0) -> str:
    """환각·무음 결과를 걸러 낸다. 버릴 결과면 빈 문자열."""
    t = (text or "").strip()
    if not t or no_speech_prob > NO_SPEECH_THRESHOLD:
        return ""
    if len(t.replace(" ", "")) <= 1:
        return ""
    if any(h.lower() in t.lower() for h in HALLUCINATIONS) and len(t) <= 25:
        return ""
    return t


class MockSTT:
    """파일 이름에 따라 정해진 문장을 돌려준다. 예: delivery.wav -> "택배 왔습니다" """
    name = "mock-stt"
    SAMPLES = {
        "delivery": "택배 왔습니다",
        "visit": "안녕하세요 옆집인데요",
        "repair": "가스 점검 나왔습니다",
        "suspicious": "집에 아무도 없어요? 알림 보내지 마",
    }

    def transcribe(self, audio_path: Path, original_name: str = "") -> tuple[str, float]:
        name = (original_name or audio_path.name).lower()
        for key, text in self.SAMPLES.items():
            if key in name:
                return text, 0.95
        return "잘 안 들려요", 0.40


class GroqSTT:
    """Groq Whisper. language=ko 지정으로 짧은 발화의 언어 오인식을 막는다."""

    def __init__(self) -> None:
        self.name = f"groq/{settings.STT_MODEL}"

    def transcribe(self, audio_path: Path, original_name: str = "") -> tuple[str, float]:
        try:
            with open(audio_path, "rb") as f:
                res = get_client().audio.transcriptions.create(
                    model=settings.STT_MODEL,
                    file=(original_name or audio_path.name, f),
                    language=settings.STT_LANGUAGE,
                    response_format="verbose_json",
                    temperature=0,
                    timeout=settings.STT_TIMEOUT_SEC,
                )
        except Exception as e:   # 네트워크·한도 초과 등: 응대가 멈추지 않도록 빈 결과
            log.warning("STT 실패 (%s): %s", type(e).__name__, e)
            return "", 0.0

        segments = getattr(res, "segments", None) or []
        get = lambda s, k: s.get(k) if isinstance(s, dict) else getattr(s, k, None)
        no_speech = max((get(s, "no_speech_prob") or 0.0 for s in segments), default=0.0)
        logprobs = [get(s, "avg_logprob") for s in segments if get(s, "avg_logprob") is not None]
        confidence = round(min(1.0, math.exp(sum(logprobs) / len(logprobs))), 3) if logprobs else 0.8

        text = clean_transcript(getattr(res, "text", ""), no_speech)
        if not text:
            log.info("STT 결과 버림 (무음·환각 의심): %r no_speech=%.2f", getattr(res, "text", ""), no_speech)
            return "", 0.0
        return text, confidence


def get_stt():
    if settings.STT_BACKEND == "groq":
        if groq_ready():
            return GroqSTT()
        log.warning("STT_BACKEND=groq 이지만 GROQ_API_KEY가 없어 Mock STT로 동작합니다")
    return MockSTT()


stt = get_stt()
