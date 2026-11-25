"""피드백 대기 중인 이벤트의 features 보관소.

finalize가 끝나면 그 이벤트의 features 한 줄(13개 값)만 파일에 남긴다.
프레임별 Vision 결과·음성 원문은 남기지 않는다.
사용자 피드백이 오면 꺼내서 RAG 사례로 옮기고 여기서는 지운다.
피드백이 오지 않은 기록은 PENDING_KEEP_DAYS(기본 7일)가 지나면 지운다.
"""
import json
import logging
import threading
import time

from app.config import settings
from app.schemas import EventFeatures

log = logging.getLogger("pending")


def now() -> float:   # 테스트에서 시간을 바꿀 수 있게 분리
    return time.time()


class PendingStore:
    def __init__(self, path, keep_days: int) -> None:
        self.path = path
        self.keep_sec = keep_days * 86400
        self.lock = threading.Lock()
        self.items: dict[str, dict] = {}
        if path.exists():
            try:
                self.items = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                log.warning("피드백 대기 파일을 읽지 못해 새로 시작합니다: %s", path)
        with self.lock:
            if self._cleanup():
                self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)   # 쓰는 도중 꺼져도 파일이 깨지지 않게

    def _cleanup(self) -> int:
        limit = now() - self.keep_sec
        old = [k for k, v in self.items.items() if v.get("saved_at", 0) < limit]
        for k in old:
            del self.items[k]
        if old:
            log.info("피드백 없이 %d일 지난 이벤트 %d건 삭제", self.keep_sec // 86400, len(old))
        return len(old)

    def save(self, event_id: int, features: EventFeatures) -> None:
        with self.lock:
            self._cleanup()
            self.items[str(event_id)] = {"saved_at": now(), "features": features.model_dump(mode="json")}
            self._save()

    def get(self, event_id: int) -> EventFeatures | None:
        item = self.items.get(str(event_id))
        return EventFeatures.model_validate(item["features"]) if item else None

    def remove(self, event_id: int) -> None:
        with self.lock:
            if self.items.pop(str(event_id), None) is not None:
                self._save()

    def __len__(self) -> int:
        return len(self.items)


pending_store = PendingStore(settings.PENDING_PATH, settings.PENDING_KEEP_DAYS)
