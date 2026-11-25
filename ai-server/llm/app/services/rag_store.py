"""RAG 사례 저장소 (ADR-03). DB 없이 JSON 파일로 관리한다.

구조화된 피처(숫자·참거짓·범주) 사이의 가중 거리로 유사 사례를 찾는다.
표 형태 데이터라 문장 임베딩보다 정확하고, 외부 API 호출이 없어 빠르다.
"""
import json
import threading
import uuid

from app.config import settings
from app.schemas import EventFeatures, UserLabel

VISION_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


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

    def find_by_event(self, event_id: int) -> dict | None:
        return next((c for c in self.cases if c.get("event_id") == event_id and event_id > 0), None)

    def update_label(self, event_id: int, label: UserLabel, memo: str | None = None) -> str | None:
        """같은 이벤트에 평가가 다시 오면(사용자가 수정) 새로 추가하지 않고 라벨만 바꾼다."""
        with self.lock:
            case = self.find_by_event(event_id)
            if case is None:
                return None
            case["label"] = label.value
            if memo:
                case["memo"] = memo
            self._save()
            return case["case_id"]

    def add(self, event_id: int, features: EventFeatures, label: UserLabel, memo: str | None = None) -> str:
        case = {
            "case_id": f"case_{uuid.uuid4().hex[:8]}",
            "event_id": event_id,
            "memo": memo or "",
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
        """유사 사례 k개. 라벨별로 고르게 섞어서 한쪽으로 쏠리지 않게 한다.

        거리 = 항목별 차이(0~1)에 가중치를 곱해 더한 값. 작을수록 비슷하다.
        Vision 신호(흉기·얼굴 가림·Vision 위험도)는 위험도와 직결되므로 가중치를 크게 준다.
        예전 사례에 없는 항목은 기본값(없음)으로 본다.
        """
        return self._pick(self.rank(features), k)

    @staticmethod
    def distance(cf: dict, f: EventFeatures) -> float:
        g = lambda key, default=0: cf.get(key, default)
        hour_gap = min(abs(g("hour") - f.hour), 24 - abs(g("hour") - f.hour)) / 12
        v_level = lambda lv: VISION_ORDER.get(lv or "LOW", 0)
        return (
            2.0 * (g("weapon_detected", False) != f.weapon_detected)
            + 1.5 * (g("face_covered", False) != f.face_covered)
            + 1.5 * abs(v_level(g("vision_risk_level", None)) - v_level(
                f.vision_risk_level.value if f.vision_risk_level else None)) / 2
            + 1.5 * hour_gap
            + 1.0 * min(abs(g("stay_sec") - f.stay_sec), 300) / 300
            + 1.0 * (g("purpose", "UNKNOWN") != f.purpose.value)
            + 1.0 * (g("package_detected", False) != f.package_detected)
            + 0.5 * (g("doorbell_pressed", False) != f.doorbell_pressed)
            + 0.5 * min(abs(g("repeat_24h") - f.repeat_24h), 3) / 3
            + 0.5 * min(abs(g("shock_count") - f.shock_count), 5) / 5
        )

    def rank(self, features: EventFeatures) -> list[dict]:
        return sorted(self.cases, key=lambda c: self.distance(c["features"], features))

    @staticmethod
    def _pick(ranked: list[dict], k: int) -> list[dict]:
        """가까운 순으로 고르되 라벨당 최대 2개. 그래도 k개가 안 되면 남은 가까운 사례로 채운다."""
        ranked = ranked[: k * 4]
        picked, per_label = [], {}
        for c in ranked:
            if per_label.get(c["label"], 0) < 2:
                picked.append(c)
                per_label[c["label"]] = per_label.get(c["label"], 0) + 1
            if len(picked) == k:
                break
        for c in ranked:
            if len(picked) == k:
                break
            if c not in picked:
                picked.append(c)
        return picked

    def __len__(self) -> int:
        return len(self.cases)


case_store = CaseStore(settings.CASES_PATH)
