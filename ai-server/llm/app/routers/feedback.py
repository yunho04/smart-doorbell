"""POST /api/v1/feedback : 사용자 위험도 평가를 RAG 사례 저장소에 추가.

MVP v1 명세에는 없는 후속 단계용 API. Spring이 사용자 평가 기능을 만들면 연결한다.
"""
from fastapi import APIRouter, Depends

from app.schemas import FeedbackRequest, FeedbackResponse
from app.security import verify_internal_token
from app.services.rag_store import case_store

router = APIRouter(tags=["feedback (후속 단계)"], dependencies=[Depends(verify_internal_token)])


@router.post("/api/v1/feedback", response_model=FeedbackResponse)
def add_feedback(req: FeedbackRequest):
    case_id = case_store.add(req.event_id, req.features, req.user_label)
    return FeedbackResponse(case_id=case_id, total_cases=len(case_store))
