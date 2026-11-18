"""LLM 호출부. 방문 목적 분류 / 위험도 판단 / 요약 세 가지 기능을 제공한다.

지금은 규칙으로 흉내 내는 Mock. 실제 구현 시 RealLLM의 메서드만 채우면
라우터 코드는 바꾸지 않아도 된다.
"""
from app.config import settings
from app.schemas import EventFeatures, Purpose, RiskLevel


class MockLLM:
    model_name = "mock-llm"

    # ----- 방문 목적 분류 (FR-06) -----
    def classify_purpose(self, transcript: str) -> tuple[Purpose, float]:
        rules = [
            (Purpose.DELIVERY, ["택배", "배달", "배송", "소포"]),
            (Purpose.REPAIR, ["점검", "수리", "검침", "가스", "관리실"]),
            (Purpose.VISIT, ["안녕하세요", "옆집", "친구", "방문"]),
        ]
        for purpose, words in rules:
            if any(w in transcript for w in words):
                return purpose, 0.9
        return Purpose.UNKNOWN, 0.3

    # ----- 위험도 판단 (FR-02, RAG) -----
    def assess_risk(
        self, features: EventFeatures, transcripts: list[str], examples: list[dict]
    ) -> tuple[RiskLevel, str, float]:
        score = 0
        reasons = []
        if features.hour < 6 or features.hour >= 23:
            score += 1; reasons.append("심야 시간대 방문")
        if features.stay_sec >= 120:
            score += 1; reasons.append(f"장시간 체류({features.stay_sec}초)")
        if features.repeat_24h >= 2:
            score += 1; reasons.append(f"24시간 내 반복 접근 {features.repeat_24h}회")
        if features.shock_count >= 2:
            score += 2; reasons.append(f"문 충격 {features.shock_count}회")
        if not features.doorbell_pressed and features.stay_sec >= 60:
            score += 1; reasons.append("응대 없이 오래 머무름")
        if features.package_detected and features.purpose == Purpose.DELIVERY:
            score -= 1; reasons.append("택배 상자 감지 및 택배 목적 확인")

        level = RiskLevel.HIGH if score >= 3 else RiskLevel.MEDIUM if score >= 1 else RiskLevel.LOW
        reason = ", ".join(reasons) or "특이사항 없음"
        if examples:
            reason += f" (유사 사례 {len(examples)}건 참고)"
        return level, reason, 0.7

    # ----- 상황 요약 (FR-03) -----
    def summarize(self, features: EventFeatures, transcripts: list[str], risk_level,
                  vision_reasons: list[str] | None = None) -> str:
        who = "택배 기사로 보이는 방문자" if features.purpose == Purpose.DELIVERY else "방문자"
        parts = [f"{features.hour}시에 {who}가 약 {features.stay_sec}초간 머물렀습니다."]
        if vision_reasons:
            parts.append(f"영상 분석: {', '.join(vision_reasons)}.")
        elif features.package_detected:
            parts.append("택배 상자가 감지되었습니다.")
        if features.shock_count:
            parts.append(f"문에 충격이 {features.shock_count}회 감지되었습니다.")
        if transcripts:
            parts.append(f"방문자 발화: \"{transcripts[-1]}\".")
        if risk_level:
            parts.append(f"위험도는 {risk_level.value}입니다.")
        return " ".join(parts)


class RealLLM:
    """TODO: 사용할 LLM SDK 연결 (openai / anthropic / google-genai 중 택1).

    구현 시 주의 (NFR-01):
    - 방문자 발화는 <visitor_transcript> 태그로 감싸 '데이터'로만 전달하고,
      태그 안의 지시는 따르지 말라고 시스템 프롬프트에 명시
    - 응답은 JSON 형식으로 받고 Pydantic으로 검증
    - 타임아웃 3초, 실패 시 예외 -> 라우터에서 503 응답
    """

    def __init__(self) -> None:
        raise NotImplementedError("LLM SDK 연결 후 사용")


def get_llm():
    if settings.LLM_BACKEND != "mock":
        return RealLLM()
    return MockLLM()


llm = get_llm()
