"""「LLM 연동 API 명세서 MVP v1」 흐름 테스트.

1) Spring이 eventId 발급 (테스트에서는 숫자를 직접 사용)
2) Vision -> AI : 프레임 결과       POST /api/v1/events/{id}/vision
3) Pi B -> AI  : 음성 -> STT -> 대사 선택 -> Spring /response
4) Spring -> AI: POST /api/v1/events/{id}/finalize
5) AI -> Spring: POST /api/v1/events/{id}/result {riskLevel, summary}
"""
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import event_cache as cache_module
from app.services.event_cache import event_cache

client = TestClient(app)
BASE = datetime(2026, 11, 18, 14, 0, 0)


CLOCK = {"t": BASE}


@pytest.fixture(autouse=True)
def spring(monkeypatch):
    """Spring 호출을 가로채서 기록하고, AI 서버 수신 시각을 테스트에서 조절한다."""
    event_cache.clear()
    CLOCK["t"] = BASE
    monkeypatch.setattr(cache_module, "now", lambda: CLOCK["t"])
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers})
        return httpx.Response(201, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


def vision(eid, frame_no, sec, person=True, package=False, conf=0.9, level="LOW",
           reasons=None, face=False, weapons=None, visible=None, start=BASE):
    """Vision 담당 코드(app.py)가 실제로 보내는 JSON 형식 그대로."""
    CLOCK["t"] = start + timedelta(seconds=sec)          # 이 시각에 AI 서버가 수신한 것으로 처리
    return client.post("/vision/result", json={
        "event_id": eid, "frame_no": frame_no,
        "person_detected": person, "person_count": 1 if person else 0,
        "objects": [{"label": "person", "confidence": conf, "bbox": [0, 0, 10, 10]}] if person else [],
        "processing_ms": 500,
        "person_visible_sec": sec if visible is None else visible,
        "package_detected": package, "face_covered": face, "weapon_labels": weapons or [],
        "vision_risk_level": level, "vision_reasons": reasons or [],
    })


def audio(eid, name):
    return client.post(f"/api/v1/events/{eid}/audio",
                       files={"file": (name, b"fake-audio", "audio/wav")})


def finalize(eid, body_id=None):
    return client.post(f"/api/v1/events/{eid}/finalize", json={"eventId": body_id or eid})


def calls_to(calls, suffix):
    return [c for c in calls if c["url"].endswith(suffix)]


# ---------- 상태 ----------
def test_health():
    assert client.get("/health").json()["status"] == "ok"


# ---------- 명세서 3장: 중간 대사 -> Spring /response ----------
def test_audio_delivery_sends_response_to_spring(spring):
    body = audio(15, "delivery.wav").json()
    assert body["responseCode"] == "DELIVERY_01" and body["sentToSpring"] is True

    sent = calls_to(spring, "/api/v1/events/15/response")
    assert len(sent) == 1
    assert sent[0]["url"] == "http://spring.test:8080/api/v1/events/15/response"
    assert sent[0]["json"] == {"responseCode": "DELIVERY_01",
                               "responseText": "택배는 문 앞에 놓아 주세요. 감사합니다."}


def test_audio_unknown_asks_again_then_handover(spring):
    assert audio(16, "noise.wav").json()["responseCode"] == "ASK_AGAIN_01"
    assert audio(16, "noise.wav").json()["responseCode"] == "ASK_AGAIN_01"
    last = audio(16, "noise.wav").json()
    assert last["turnNo"] == 3 and last["responseCode"] == "HANDOVER_01" and last["isLastTurn"]


def test_audio_bad_format():
    r = client.post("/api/v1/events/17/audio", files={"file": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 400 and r.json()["error_code"] == "HTTP_400"


def test_spring_down_does_not_break_audio(monkeypatch):
    def down(*a, **k):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "post", down)
    r = audio(18, "delivery.wav")
    assert r.status_code == 200 and r.json()["sentToSpring"] is False


# ---------- 명세서 4~5장: finalize -> /result ----------
def test_full_flow_delivery_low(spring):
    vision(20, 1, 0, conf=0.8)
    vision(20, 2, 5, package=True, conf=0.95, reasons=["택배 상자 보임"])
    audio(20, "delivery.wav")

    r = finalize(20)
    assert r.status_code == 202 and r.json() == {"eventId": 20, "status": "ACCEPTED"}

    result = calls_to(spring, "/api/v1/events/20/result")
    assert len(result) == 1
    payload = result[0]["json"]
    assert {"riskLevel", "summary"} <= set(payload)            # 명세서 필수 필드
    assert payload["responseCode"] == "DELIVERY_01"           # Spring DTO가 받는 선택 필드
    assert payload["riskLevel"] == "LOW"
    assert "택배" in payload["summary"]


def test_vision_high_cannot_be_lowered(spring):
    """Vision이 흉기를 봐서 HIGH면, 택배라고 말해도 최종 위험도는 HIGH (NFR-01)."""
    vision(27, 1, 0, package=True)
    vision(27, 2, 2, package=True, level="HIGH", weapons=["knife"], reasons=["흉기 의심: knife"])
    audio(27, "delivery.wav")
    finalize(27)
    payload = calls_to(spring, "/api/v1/events/27/result")[0]["json"]
    assert payload["riskLevel"] == "HIGH"
    assert "흉기 의심" in payload["summary"]


def test_vision_latest_endpoint():
    vision(28, 1, 0)
    vision(28, 2, 1, level="MEDIUM", face=True, reasons=["얼굴 가림: helmet"])
    latest = client.get("/vision/result/28").json()
    assert latest["frame_no"] == 2 and latest["vision_risk_level"] == "MEDIUM"


def test_full_flow_long_stay_high(spring):
    night = datetime(2026, 11, 18, 3, 0, 0)
    vision(21, 1, 0, start=night)
    vision(21, 30, 150, start=night, level="MEDIUM", reasons=["150초 머묾"])   # 150초 머무름, 말 없음
    finalize(21)
    payload = calls_to(spring, "/api/v1/events/21/result")[0]["json"]
    assert payload["riskLevel"] in ("MEDIUM", "HIGH")


def test_finalize_only_once(spring):
    audio(22, "delivery.wav")
    assert finalize(22).status_code == 202
    second = finalize(22)
    assert second.status_code == 200 and second.json()["status"] == "ALREADY_FINALIZED"
    assert len(calls_to(spring, "/api/v1/events/22/result")) == 1


def test_finalize_without_data_still_sends_result(spring):
    finalize(23)
    payload = calls_to(spring, "/api/v1/events/23/result")[0]["json"]
    assert payload["riskLevel"] == "LOW" and "데이터가 없습니다" in payload["summary"]


def test_finalize_id_mismatch():
    assert finalize(24, body_id=999).status_code == 400


def test_after_finalize_audio_rejected_and_vision_ignored():
    finalize(25)
    assert audio(25, "delivery.wav").status_code == 409
    assert vision(25, 1, 0).json()["ok"] is False


# ---------- 디버깅 / 대표 프레임 ----------
def test_state_and_best_frame():
    vision(30, 1, 0, conf=0.5)
    vision(30, 2, 3, conf=0.97, level="MEDIUM", face=True, reasons=["얼굴 가림: helmet"])
    vision(30, 3, 6, person=False, visible=3)
    audio(30, "visit.wav")
    s = client.get("/api/v1/events/30/state").json()
    assert s["visionUpdates"] == 3 and s["audioTurns"] == 1
    assert s["bestFrameNo"] == 2
    assert s["features"]["staySec"] == 6 and s["features"]["faceCovered"] is True
    assert s["features"]["visionRiskLevel"] == "MEDIUM"


# ---------- 인증 (후속 단계에서 켤 때) ----------
def test_auth_when_enabled(monkeypatch):
    from app import security
    monkeypatch.setattr(security.settings, "INTERNAL_TOKEN", "tok")
    assert finalize(40).status_code == 401
    r = client.post("/api/v1/events/40/finalize", json={"eventId": 40}, headers={"X-Internal-Token": "tok"})
    assert r.status_code == 202


# ---------- 피드백 (후속 단계) ----------
def test_feedback_adds_case():
    audio(50, "delivery.wav")
    features = client.get("/api/v1/events/50/state").json()["features"]
    before = client.get("/health").json()["rag_cases"]
    r = client.post("/api/v1/feedback", json={"eventId": 50, "features": features, "userLabel": "NORMAL"})
    assert r.status_code == 200 and r.json()["totalCases"] == before + 1
