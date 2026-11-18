"""finalize 시 최종 분석 (명세서 4장 LLM 동작).

eventId에 대해 AI 파트가 보유한 Vision 결과와 STT 기록을 종합해
최종 위험도와 요약을 만들고 Spring /result로 보낸다.

최종 위험도 = max(Vision 1차 위험도, LLM 2차 판단)
-> 흉기·얼굴 가림처럼 Vision이 HIGH로 본 상황을 LLM이 낮추지 못하게 한다 (NFR-01).
"""
import logging
from datetime import datetime

from app.config import settings
from app.schemas import EventFeatures, Purpose, RiskLevel, SpringResultRequest
from app.services.event_cache import EventData, event_cache
from app.services.llm import llm
from app.services.rag_store import case_store
from app.services.spring_client import send_result

log = logging.getLogger("ai-llm")

LEVEL_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}


def max_level(*levels: RiskLevel | None) -> RiskLevel:
    return max((lv for lv in levels if lv), key=LEVEL_ORDER.get, default=RiskLevel.LOW)


def build_features(data: EventData) -> EventFeatures:
    """Vision 누적 결과와 음성 기록으로 판단용 피처를 만든다.

    MVP v1에서는 Spring이 센서 값을 보내지 않으므로
    충격 횟수·반복 접근은 0, 초인종은 '음성 응대가 있었는지'로 대체한다.
    """
    times = sorted(data.observed_at) or [datetime.now()]
    v = data.latest_vision
    spoken = [x for x in data.voices if x.purpose != Purpose.UNKNOWN]
    last_voice = spoken[-1] if spoken else (data.voices[-1] if data.voices else None)
    visible_sec = max((x.person_visible_sec for x in data.visions), default=0)

    return EventFeatures(
        hour=times[0].hour,
        # Vision은 바뀔 때만 보내므로 수신 시각 간격과 Vision의 '사람 보인 시간' 중 큰 값 사용
        stay_sec=max(int((times[-1] - times[0]).total_seconds()), visible_sec),
        doorbell_pressed=bool(data.voices),
        person_count=max((x.person_count for x in data.visions), default=0),
        person_visible_sec=visible_sec,
        package_detected=v.package_detected if v else False,
        face_covered=any(x.face_covered for x in data.visions),
        weapon_detected=any(x.weapon_labels for x in data.visions),
        vision_risk_level=max_level(*(x.vision_risk_level for x in data.visions)) if data.visions else None,
        purpose=last_voice.purpose if last_voice else Purpose.UNKNOWN,
        purpose_confidence=last_voice.purpose_confidence if last_voice else 0.0,
    )


def select_best_frame(data: EventData) -> int | None:
    """대표 프레임: Vision이 보낸 결과 중 사람 인식 신뢰도가 가장 높은 사진의 frame_no (명세서 6장)."""
    def person_conf(v) -> float:
        return max((o.confidence for o in v.objects if o.label == "person"), default=0.0)

    candidates = [v for v in data.visions if v.person_detected] or data.visions
    return max(candidates, key=person_conf).frame_no if candidates else None


def vision_reasons(data: EventData) -> list[str]:
    v = data.latest_vision
    return list(v.vision_reasons) if v else []


def analyze(event_id: int) -> tuple[SpringResultRequest, dict]:
    """최종 위험도·요약을 만든다. (Spring 전송은 하지 않음)"""
    data = event_cache.get(event_id)
    if not data.visions and not data.voices:
        result = SpringResultRequest(risk_level=RiskLevel.LOW, summary="분석할 영상·음성 데이터가 없습니다.")
        return result, {"reason": "데이터 없음", "referenced_case_ids": [], "best_frame_no": None}

    features = build_features(data)
    transcripts = [x.transcript for x in data.voices]

    # 1) Retrieval: 유사 사례 검색  2) Generation: LLM 2차 판단
    examples = case_store.search(features, k=settings.RAG_TOP_K)
    llm_level, reason, _conf = llm.assess_risk(features, transcripts, examples)

    # 3) Vision 1차 위험도보다 낮출 수 없음
    final_level = max_level(llm_level, features.vision_risk_level)
    reasons_v = vision_reasons(data)
    if reasons_v:
        reason = f"Vision: {', '.join(reasons_v)} / LLM: {reason}"

    summary = llm.summarize(features, transcripts, final_level, reasons_v)
    detail = {
        "reason": reason,
        "vision_level": features.vision_risk_level.value if features.vision_risk_level else None,
        "llm_level": llm_level.value,
        "referenced_case_ids": [c["case_id"] for c in examples],
        "best_frame_no": select_best_frame(data),
    }
    return SpringResultRequest(risk_level=final_level, summary=summary), detail


def finalize_event(event_id: int) -> bool:
    """finalize 백그라운드 작업: 분석 후 Spring /result 전송."""
    result, d = analyze(event_id)
    log.info("최종 분석 eventId=%s risk=%s (vision=%s, llm=%s) reason=%s 참조사례=%s 대표프레임=%s",
             event_id, result.risk_level.value, d.get("vision_level"), d.get("llm_level"),
             d["reason"], d["referenced_case_ids"], d["best_frame_no"])
    # TODO: 대표 사진 업로드 (POST /api/v1/events/{id}/image) 담당은 팀에서 결정
    return send_result(event_id, result)
