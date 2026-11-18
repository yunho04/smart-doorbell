"""방문 목적 -> 사전 정의 대사 선택 (ADR-04, 명세서 3장의 responseCode).

대사 코드와 문구는 data/reply_templates.json에서 관리한다.
Pi B가 재생할 음성 파일도 같은 코드 이름으로 맞춘다 (예: DELIVERY_01.mp3).
"""
import json

from app.config import settings
from app.schemas import Purpose

TEMPLATES: dict[str, str] = json.loads(settings.TEMPLATES_PATH.read_text(encoding="utf-8"))

PURPOSE_TO_CODE = {
    Purpose.DELIVERY: "DELIVERY_01",
    Purpose.VISIT: "VISIT_01",
    Purpose.REPAIR: "REPAIR_01",
    Purpose.OTHER: "OTHER_01",
}


def select_response(purpose: Purpose, turn_no: int) -> tuple[str, bool]:
    """(대사 코드, 마지막 응대 여부)를 돌려준다."""
    if purpose == Purpose.UNKNOWN:
        if turn_no >= settings.MAX_TURNS:
            return "HANDOVER_01", True    # 최대 횟수 도달 -> 거주자에게 전달하고 종료
        return "ASK_AGAIN_01", False      # 다시 말해 달라고 요청
    return PURPOSE_TO_CODE[purpose], True
