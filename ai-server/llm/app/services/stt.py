"""STT: 음성 파일 -> 텍스트.

지금은 Mock. 실제 구현 시 WhisperSTT의 transcribe()만 채우면 된다.
"""
from pathlib import Path

from app.config import settings


class MockSTT:
    """파일 이름에 따라 정해진 문장을 돌려준다 (흐름 테스트용).

    예: delivery.wav -> "택배 왔습니다"
    """
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


class WhisperSTT:
    """TODO: faster-whisper 연결.

    from faster_whisper import WhisperModel
    self.model = WhisperModel("small", device="cpu", compute_type="int8")  # 서버 시작 시 1회 로딩
    segments, info = self.model.transcribe(str(audio_path), language="ko", vad_filter=True)
    """

    def __init__(self) -> None:
        raise NotImplementedError("faster-whisper 연결 후 사용")

    def transcribe(self, audio_path: Path, original_name: str = "") -> tuple[str, float]:
        raise NotImplementedError


def get_stt():
    if settings.STT_BACKEND == "whisper":
        return WhisperSTT()
    return MockSTT()


stt = get_stt()
