"""RAG 사례 저장소 (ADR-03). DB 없이 JSON 파일로 관리한다.

지금은 피처 간 거리로 유사 사례를 찾는 임시 구현.
TODO: 상황 문장 임베딩 + 코사인 유사도(numpy)로 교체.
"""
import json
import threading
import uuid

from app.config import settings
from app.schemas import EventFeatures, UserLabel


def features_to_text(f: EventFeatures) -> str:
    """임베딩용 상황 설명 문장. (숫자를 그대로 임베딩하지 않고 문장으로 변환)"""
    return (
        f"{f.hour}시 방문, {f.stay_sec}초 체류, 24시간 내 {f.repeat_24h}회 접근, "
        f"충격 {f.shock_count}회, 초인종 {'누름' if f.doorbell_pressed else '누르지 않음'}, "
        f"택배 상자 {'있음' if f.package_detected else '없음'}, "
        f"얼굴 가림 {'있음' if f.face_covered else '없음'}, 흉기 의심 {'있음' if f.weapon_detected else '없음'}, "
        f"방문 목적 {f.purpose.value}"
    )


class CaseStore:
    def __init__(self, path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.cases: list[dict] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.cases, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, event_id: int, features: EventFeatures, label: UserLabel) -> str:
        case = {
            "case_id": f"case_{uuid.uuid4().hex[:8]}",
            "event_id": event_id,
            "text": features_to_text(features),
            "features": features.model_dump(mode="json"),  # snake_case로 저장
            "label": label.value,
            # "embedding": [...]  TODO: 임베딩 벡터 저장
        }
        with self.lock:
            self.cases.append(case)
            self._save()
        return case["case_id"]

    def search(self, features: EventFeatures, k: int) -> list[dict]:
        """유사 사례 k개. 라벨별로 고르게 섞어서 한쪽으로 쏠리지 않게 한다."""
        def distance(c: dict) -> float:
            cf = c["features"]
            hour_gap = min(abs(cf["hour"] - features.hour), 24 - abs(cf["hour"] - features.hour))
            return (
                hour_gap / 12
                + min(abs(cf["stay_sec"] - features.stay_sec), 300) / 300
                + min(abs(cf["shock_count"] - features.shock_count), 5) / 5
                + (cf["doorbell_pressed"] != features.doorbell_pressed)
                + (cf["package_detected"] != features.package_detected)
                + (cf["purpose"] != features.purpose.value)
            )

        ranked = sorted(self.cases, key=distance)[: k * 4]
        picked, per_label = [], {}
        for c in ranked:  # 라벨당 최대 2개
            if per_label.get(c["label"], 0) < 2:
                picked.append(c)
                per_label[c["label"]] = per_label.get(c["label"], 0) + 1
            if len(picked) == k:
                break
        return picked

    def __len__(self) -> int:
        return len(self.cases)


case_store = CaseStore(settings.CASES_PATH)
