"""시나리오 데이터. 결과 JSON 은 backend 의 EventResultRequest 규격을 따른다.

responseCode 값은 저장소에 확정 목록 문서가 없어 기존 DB 에서 쓰인 형식(XXX_01)을 따른 테스트용 값이다.
summary 앞의 [통합테스트] 로 대시보드에서 테스트 이벤트를 구분할 수 있다.
"""
from dataclasses import dataclass

TAG = "[통합테스트] "


def turn(no, visitor, purpose, code, text):
    return {"turnNo": no, "visitorText": visitor, "purpose": purpose, "responseCode": code, "responseText": text}


@dataclass
class Visit:
    risk: str
    summary: str
    code: str
    text: str
    purpose: str
    conversation_summary: str
    conversation: list
    feedback: str
    live_response: tuple = None   # 방문 중 LLM 이 보내는 실시간 응답 (responseCode, responseText)

    def result(self):
        return {"riskLevel": self.risk, "summary": TAG + self.summary, "responseCode": self.code,
                "responseText": self.text, "purpose": self.purpose,
                "conversationSummary": self.conversation_summary, "conversation": self.conversation}


DELIVERY = Visit(
    "LOW", "택배 기사가 물품을 문 앞에 두고 떠났습니다.", "DELIVERY_01", "문 앞에 두고 가시면 됩니다. 감사합니다.",
    "택배 배송", "방문자가 택배 배송을 알렸고 문 앞에 두도록 안내했습니다.",
    [turn(1, "택배 왔습니다.", "택배 배송", "DELIVERY_01", "안녕하세요. 어떤 택배인가요?"),
     turn(2, "최윤호 님 앞으로 온 소포입니다.", "택배 배송", "DELIVERY_01", "문 앞에 두고 가시면 됩니다. 감사합니다.")],
    "HIGH")

UNCLEAR = Visit(
    "MEDIUM", "방문 목적을 밝히지 않은 방문자가 머물다 떠났습니다.", "ASK_AGAIN_01", "방문 목적을 다시 말씀해 주시겠어요?",
    "목적 불분명", "방문 목적을 두 차례 물었으나 명확한 답을 듣지 못했습니다.",
    [turn(1, "저기요, 계세요?", None, "ASK_AGAIN_01", "안녕하세요. 어떤 일로 오셨나요?"),
     turn(2, "아... 그냥요.", "목적 불분명", "ASK_AGAIN_01", "방문 목적을 다시 말씀해 주시겠어요?"),
     turn(3, "", "목적 불분명", "OTHER_01", "용건이 없으시면 응대를 종료하겠습니다.")],
    "MEDIUM", live_response=("ASK_AGAIN_01", "안녕하세요. 어떤 일로 오셨나요?"))

HIGH_RISK = Visit(
    "HIGH", "방문자가 문을 열라고 반복 요구하며 문 앞을 서성였습니다.", "WARNING_01", "지금은 응대가 어렵습니다. 돌아가 주세요.",
    "출입 강요", "신원을 밝히지 않은 채 문 개방을 반복 요구해 경고 후 응대를 종료했습니다.",
    [turn(1, "문 좀 열어 봐요.", "출입 요구", "ASK_AGAIN_01", "누구신지 말씀해 주시겠어요?"),
     turn(2, "빨리 열라고!", "출입 강요", "WARNING_01", "지금은 응대가 어렵습니다. 돌아가 주세요.")],
    "LOW")

ACQUAINTANCE = Visit(
    "LOW", "이웃 주민이 관리비 안내문을 전달하러 방문했습니다.", "OTHER_01", "안내문은 우편함에 넣어 주세요. 감사합니다.",
    "이웃 방문", "옆집 주민이 안내문 전달을 위해 방문했습니다.",
    [turn(1, "옆집인데요, 안내문 드리러 왔어요.", "이웃 방문", "OTHER_01", "안내문은 우편함에 넣어 주세요. 감사합니다.")],
    "HIGH")

SCENARIOS = {
    "delivery": "정상적인 택배 기사 방문",
    "unclear": "방문 목적이 불분명한 방문자",
    "high-risk": "위험도가 높은 방문자",
    "consecutive": "연속 방문",
    "duplicate": "동일 이벤트 결과 중복 전송",
}
