"""API 요청/응답 형식.

- Spring과 주고받는 형식: 「LLM 연동 API 명세서 MVP v1」 기준 (camelCase)
- Vision -> AI : Vision 담당 코드의 형식 그대로 (snake_case, POST /vision/result)
- Pi B -> AI  : AI 파트 내부 규약 (명세서에 없음, Pi 담당과 공유 필요)
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """JSON에서는 camelCase(eventId), 파이썬 코드에서는 snake_case(event_id)로 쓴다."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ---------- 공통 코드값 ----------
class Purpose(str, Enum):
    DELIVERY = "DELIVERY"
    VISIT = "VISIT"
    REPAIR = "REPAIR"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class UserLabel(str, Enum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    DANGER = "DANGER"


# =====================================================================
# Spring <-> LLM (명세서 MVP v1)
# =====================================================================
class FinalizeRequest(CamelModel):
    """Spring -> LLM : POST /api/v1/events/{eventId}/finalize"""
    event_id: int


class FinalizeAck(CamelModel):
    event_id: int
    status: str = Field(..., description="ACCEPTED | ALREADY_FINALIZED")


class SpringResponseRequest(CamelModel):
    """LLM -> Spring : POST /api/v1/events/{eventId}/response"""
    response_code: str
    response_text: str


class SpringResultRequest(CamelModel):
    """LLM -> Spring : POST /api/v1/events/{eventId}/result

    명세서 필수: riskLevel, summary
    Spring 실제 DTO(EventResultRequest)는 responseCode, responseText도 받아 events 행에 저장한다.
    -> 마지막으로 재생한 대사를 함께 보낸다 (응대가 없었으면 null).
    """
    risk_level: RiskLevel
    summary: str
    response_code: str | None = None
    response_text: str | None = None


# =====================================================================
# Vision / Pi B -> AI 서버
# =====================================================================
class DetectedObject(BaseModel):
    label: str
    confidence: float = Field(..., ge=0, le=1)
    bbox: list[float] = Field(default_factory=list, description="[x1, y1, x2, y2] 픽셀")


class VisionResult(BaseModel):
    """Vision 서버 -> AI 서버 : POST /vision/result

    Vision 담당(장준용) 코드의 전송 형식을 그대로 받는다 (snake_case).
    Vision은 위험도나 확인된 라벨이 바뀔 때만 보낸다 (보통 Event당 2~4번).
    """
    model_config = ConfigDict(extra="ignore")

    event_id: int
    frame_no: int = Field(..., description="이 Event에서 몇 번째 사진인지")
    # 이번 사진
    person_detected: bool = False
    person_count: int = Field(0, ge=0)
    objects: list[DetectedObject] = Field(default_factory=list)
    processing_ms: int = 0
    # Event 누적 (Vision이 2장 이상에서 확인한 것만)
    person_visible_sec: int = Field(0, ge=0)
    package_detected: bool = False
    face_covered: bool = False
    weapon_labels: list[str] = Field(default_factory=list)
    vision_risk_level: "RiskLevel" = Field(..., description="Vision 1차 위험도")
    vision_reasons: list[str] = Field(default_factory=list)


class AudioResult(CamelModel):
    """Pi B -> AI 서버 : POST /api/v1/events/{eventId}/audio 의 응답"""
    event_id: int
    turn_no: int
    transcript: str
    stt_confidence: float
    purpose: Purpose
    purpose_confidence: float
    response_code: str
    response_text: str
    sent_to_spring: bool
    is_last_turn: bool
    processing_ms: int


class Ack(CamelModel):
    event_id: int
    received: bool = True


# =====================================================================
# 판단용 피처 / RAG
# =====================================================================
class EventFeatures(CamelModel):
    """Vision·STT 결과로 만든 판단용 피처 (RAG 사례 저장 형식)."""
    hour: int = Field(..., ge=0, le=23)
    stay_sec: int = Field(0, ge=0, description="첫 관측~마지막 관측 (Vision·음성 기준)")
    repeat_24h: int = Field(0, ge=0, alias="repeat24h", description="MVP: 정보 없음 -> 0")
    shock_count: int = Field(0, ge=0, description="MVP: 충격 센서 정보 없음 -> 0")
    doorbell_pressed: bool = Field(False, description="MVP: 초인종 정보 없음 -> 음성 응대 여부로 대체")
    person_count: int = Field(0, ge=0)
    person_visible_sec: int = Field(0, ge=0)
    package_detected: bool = False
    face_covered: bool = Field(False, description="Vision: 헬멧·마스크·복면")
    weapon_detected: bool = Field(False, description="Vision: 흉기 의심")
    vision_risk_level: RiskLevel | None = Field(None, description="Vision 1차 위험도")
    purpose: Purpose = Purpose.UNKNOWN
    purpose_confidence: float = Field(0.0, ge=0, le=1)


class FeedbackRequest(CamelModel):
    """후속 단계용 (MVP 명세에는 없음)"""
    event_id: int
    features: EventFeatures
    user_label: UserLabel


class FeedbackResponse(CamelModel):
    case_id: str
    total_cases: int


class EventState(CamelModel):
    """디버깅용 : GET /api/v1/events/{eventId}/state"""
    event_id: int
    vision_updates: int
    audio_turns: int
    transcripts: list[str]
    vision_reasons: list[str]
    best_frame_no: int | None
    finalized: bool
    features: EventFeatures | None
