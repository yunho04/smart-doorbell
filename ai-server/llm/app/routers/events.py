"""이벤트 단위 API. 모든 경로는 Spring이 발급한 eventId를 기준으로 한다.

[Spring -> LLM]  POST /api/v1/events/{eventId}/finalize   종료 신호 (명세서 4장)
[Pi B -> AI]     POST /api/v1/events/{eventId}/audio      방문자 음성 (내부 규약)
[디버깅]          GET  /api/v1/events/{eventId}/state      보관 중인 데이터 확인
"""
import logging
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.config import settings
from app.schemas import (AudioResult, EventState, FinalizeAck, FinalizeRequest, Purpose,
                         SpringResponseRequest)
from app.security import verify_device_key, verify_internal_token
from app.services.analyzer import build_features, finalize_event, select_best_frame, vision_reasons
from app.services.event_cache import event_cache
from app.services.llm import llm
from app.services.spring_client import send_response
from app.services.stt import stt
from app.services.templates import TEMPLATES, select_response

log = logging.getLogger("ai-llm")
router = APIRouter(prefix="/api/v1/events", tags=["events"])

ALLOWED_EXT = {".wav", ".mp3", ".m4a", ".webm"}


# ---------------------------------------------------------------------
# Spring -> LLM : 종료 신호 (Event당 1회)
# ---------------------------------------------------------------------
@router.post("/{event_id}/finalize", response_model=FinalizeAck, status_code=202,
             dependencies=[Depends(verify_internal_token)])
def finalize(event_id: int, req: FinalizeRequest, background: BackgroundTasks):
    if req.event_id != event_id:
        raise HTTPException(400, detail=f"경로 eventId({event_id})와 본문 eventId({req.event_id})가 다릅니다")

    if not event_cache.mark_finalized(event_id):
        log.warning("finalize 중복 호출 무시 eventId=%s", event_id)
        return JSONResponse(status_code=200, content=FinalizeAck(
            event_id=event_id, status="ALREADY_FINALIZED").model_dump(by_alias=True))

    # 분석은 백그라운드에서 하고 Spring에는 바로 응답 (분석 완료 후 /result로 전송)
    background.add_task(finalize_event, event_id)
    return FinalizeAck(event_id=event_id, status="ACCEPTED")


# ---------------------------------------------------------------------
# Pi B -> AI : 방문자 음성 -> STT -> 중간 대사 선택 -> Spring /response
# ---------------------------------------------------------------------
@router.post("/{event_id}/audio", response_model=AudioResult, dependencies=[Depends(verify_device_key)])
def receive_audio(event_id: int, file: UploadFile = File(..., description="방문자 음성 (wav 권장)")):
    start = time.perf_counter()

    if event_cache.get(event_id).finalized:
        raise HTTPException(409, detail="이미 종료된 이벤트입니다")

    # 1) 파일 검사 후 저장
    ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, detail=f"지원하지 않는 음성 형식: {ext}")
    turn_no = event_cache.next_turn_no(event_id)
    save_path = settings.AUDIO_DIR / f"{event_id}_{turn_no}_{uuid.uuid4().hex[:6]}{ext}"
    save_path.write_bytes(file.file.read())
    # TODO: ffmpeg로 wav 16kHz mono 변환

    # 2) STT
    transcript, stt_conf = stt.transcribe(save_path, original_name=file.filename or "")

    # 3) 방문 목적 분류 (신뢰도 낮으면 UNKNOWN, NFR-03)
    purpose, purpose_conf = llm.classify_purpose(transcript)
    if purpose_conf < settings.PURPOSE_CONF_THRESHOLD:
        purpose = Purpose.UNKNOWN

    # 4) 사전 정의 대사 선택 -> Spring /response (Spring이 MQTT로 Pi B에 전달)
    code, is_last = select_response(purpose, turn_no)
    sent = send_response(event_id, SpringResponseRequest(response_code=code, response_text=TEMPLATES[code]))

    result = AudioResult(
        event_id=event_id, turn_no=turn_no,
        transcript=transcript, stt_confidence=stt_conf,
        purpose=purpose, purpose_confidence=purpose_conf,
        response_code=code, response_text=TEMPLATES[code],
        sent_to_spring=sent, is_last_turn=is_last,
        processing_ms=int((time.perf_counter() - start) * 1000),
    )
    event_cache.add_voice(result)   # finalize 때 종합 분석에 사용
    return result


# ---------------------------------------------------------------------
# 디버깅 : 보관 중인 데이터 확인 (통합 테스트 때 유용)
# ---------------------------------------------------------------------
@router.get("/{event_id}/state", response_model=EventState)
def get_state(event_id: int):
    data = event_cache.get(event_id)
    has_data = bool(data.visions or data.voices)
    return EventState(
        event_id=event_id,
        vision_updates=len(data.visions),
        audio_turns=len(data.voices),
        transcripts=[v.transcript for v in data.voices],
        vision_reasons=vision_reasons(data),
        best_frame_no=select_best_frame(data),
        finalized=data.finalized,
        features=build_features(data) if has_data else None,
    )
