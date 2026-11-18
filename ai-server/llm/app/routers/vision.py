"""Vision 서버 -> AI 서버 : POST /vision/result

Vision 담당(장준용) 코드가 이미 이 경로와 형식으로 보내도록 되어 있다.
(Vision README: "허인혜 서버가 같은 경로로 받으면 Vision 코드는 안 바뀐다")
Vision은 위험도나 확인된 라벨이 바뀔 때만 보낸다 (보통 Event당 2~4번).
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
    event_cache.add_vision(result)
    log.info("Vision 수신 eventId=%s frame=%s %s %s", result.event_id, result.frame_no,
             result.vision_risk_level.value, result.vision_reasons)
    return {"ok": True}


@router.get("/result/{event_id}")
def latest_vision(event_id: int):
    """해당 Event의 최신 Vision 결과 (Vision 담당 mock_llm.py와 같은 확인용 API)."""
    v = event_cache.get(event_id).latest_vision
    return v.model_dump() if v else {}
