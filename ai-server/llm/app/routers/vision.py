"""Vision 서버 -> AI 서버 : POST /vision/result

Vision 담당(장준용) 코드가 이미 이 경로와 형식으로 보내도록 되어 있다.
(Vision README: "허인혜 서버가 같은 경로로 받으면 Vision 코드는 안 바뀐다")
11-17 결정: Vision은 사진마다(1초에 1번) 보낸다.
"""
import logging

from fastapi import APIRouter, Depends

from app.schemas import VisionResult
from app.security import verify_internal_token
from app.services.event_cache import event_cache

log = logging.getLogger("ai-llm")
router = APIRouter(prefix="/vision", tags=["vision"], dependencies=[Depends(verify_internal_token)])


@router.post("/result")
def receive_vision(result: VisionResult):
    if event_cache.get(result.event_id).finalized:
        log.info("종료된 이벤트의 Vision 결과 무시 eventId=%s frame=%s", result.event_id, result.frame_no)
        return {"ok": False, "reason": "already finalized"}
    prev = event_cache.get(result.event_id).latest_vision
    event_cache.add_vision(result)
    changed = prev is None or (prev.vision_risk_level, prev.vision_reasons) != (result.vision_risk_level, result.vision_reasons)
    # 매초 오므로 처음과 위험도·근거가 바뀔 때만 INFO, 나머지는 DEBUG
    (log.info if changed else log.debug)("Vision 수신 eventId=%s frame=%s person=%s %s %s",
        result.event_id, result.frame_no, result.person_count,
        result.vision_risk_level.value, result.vision_reasons)
    return {"ok": True}


@router.get("/result/{event_id}")
def latest_vision(event_id: int):
    """해당 Event의 최신 Vision 결과 (Vision 담당 mock_llm.py와 같은 확인용 API)."""
    v = event_cache.get(event_id).latest_vision
    return v.model_dump() if v else {}
