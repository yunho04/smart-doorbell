"""eventId별로 Vision 결과와 STT 결과를 보관한다.

명세서: "Vision 분석 결과와 STT 결과는 Spring이 모아서 LLM에 전달하지 않는다.
AI 파트에서 eventId 기준으로 관리하며, Spring은 종료 신호만 보낸다."

메모리에만 보관하므로 서버를 재시작하면 진행 중인 이벤트 데이터가 사라진다.
"""
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from app.config import settings
from app.schemas import AudioResult, VisionResult


def now() -> datetime:
    """관측 시각은 AI 서버 수신 시각 기준 (Pi·Vision 기기 시계가 안 맞아도 안전). 테스트에서 교체 가능."""
    return datetime.now()


@dataclass
class EventData:
    visions: list[VisionResult] = field(default_factory=list)   # Vision이 보낸 누적 결과 (보통 2~4개)
    voices: list[AudioResult] = field(default_factory=list)
    observed_at: list[datetime] = field(default_factory=list)   # 모든 수신 시각 (체류 시간 계산용)
    finalized: bool = False
    updated_at: float = field(default_factory=time.time)

    @property
    def latest_vision(self) -> VisionResult | None:
        return max(self.visions, key=lambda v: v.frame_no) if self.visions else None


class EventCache:
    def __init__(self, ttl_sec: int) -> None:
        self.ttl = ttl_sec
        self._data: dict[int, EventData] = {}
        self._lock = threading.Lock()

    def _get_or_create(self, event_id: int) -> EventData:
        self._purge()
        item = self._data.setdefault(event_id, EventData())
        item.updated_at = time.time()
        return item

    def _purge(self) -> None:
        t = time.time()
        for eid in [e for e, d in self._data.items() if t - d.updated_at > self.ttl]:
            del self._data[eid]

    def add_vision(self, result: VisionResult) -> None:
        with self._lock:
            item = self._get_or_create(result.event_id)
            item.visions.append(result)
            item.observed_at.append(now())

    def add_voice(self, result: AudioResult) -> None:
        with self._lock:
            item = self._get_or_create(result.event_id)
            item.voices.append(result)
            item.observed_at.append(now())

    def next_turn_no(self, event_id: int) -> int:
        with self._lock:
            return len(self._get_or_create(event_id).voices) + 1

    def mark_finalized(self, event_id: int) -> bool:
        """처음 종료 처리하면 True, 이미 종료된 이벤트면 False (finalize 중복 호출 방지)."""
        with self._lock:
            item = self._get_or_create(event_id)
            if item.finalized:
                return False
            item.finalized = True
            return True

    def get(self, event_id: int) -> EventData:
        with self._lock:
            self._purge()
            return self._data.get(event_id, EventData())

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


event_cache = EventCache(settings.EVENT_CACHE_TTL_SEC)
