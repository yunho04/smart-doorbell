"""POST /api/v1/feedback : 사용자 평가를 RAG 사례 저장소에 추가.

흐름: 사용자(앱) -> Spring(DB 저장) -> 이 API {eventId, userLabel, memo?}
features는 Spring이 보내지 않는다. finalize 때 LLM 서버가 저장해 둔 값(pending_store)을 꺼내 쓴다.
- 처음 온 평가: 사례 추가 후 대기 목록에서 삭제
- 같은 eventId에 다시 온 평가: 기존 사례 라벨만 수정
- 대기 목록에도 사례에도 없음(7일 지남, finalize 전 등): 404
"""
from fastapi import APIRouter, Depends, HTTPException

from app.schemas import FeedbackRequest, FeedbackResponse
from app.security import verify_internal_token
from app.services.pending_store import pending_store
from app.services.rag_store import case_store

router = APIRouter(tags=["feedback"], dependencies=[Depends(verify_internal_token)])


@router.post("/api/v1/feedback", response_model=FeedbackResponse)
def add_feedback(req: FeedbackRequest):
    case_id = case_store.update_label(req.event_id, req.user_label, req.memo)
    if case_id:
        return FeedbackResponse(case_id=case_id, total_cases=len(case_store), updated=True)

    features = pending_store.get(req.event_id)
    if features is None:
        raise HTTPException(404, detail=f"eventId {req.event_id}의 분석 기록이 없습니다 (finalize 전이거나 보관 기간이 지남)")
    case_id = case_store.add(req.event_id, features, req.user_label, req.memo)
    pending_store.remove(req.event_id)
    return FeedbackResponse(case_id=case_id, total_cases=len(case_store))
