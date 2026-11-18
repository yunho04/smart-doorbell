"""실행: python test_app.py  (또는 pytest). ultralytics 에 들어 있는 bus.jpg(사람 4명+버스)로 확인."""
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import ultralytics
from fastapi.testclient import TestClient

import app as m

client = TestClient(m.app)
BUS = Path(ultralytics.__file__).parent / "assets" / "bus.jpg"


def post(event_id, data=None, **kw):
    files = {"image": ("bus.jpg", data if data is not None else BUS.read_bytes(), "image/jpeg")}
    return client.post("/vision/analyze", data={"event_id": str(event_id)}, files=files, **kw)


def test_person_detected():
    j = post(101).json()
    assert j["event_id"] == 101 and j["frame_no"] == 1
    assert j["person_detected"] and j["person_count"] >= 3
    assert j["vision_risk_level"] == "LOW" and not j["face_covered"]


def test_judge_rules():
    assert m.judge(set(), 0) == ("LOW", [])
    assert m.judge({"person", "knife"}, 0)[0] == "HIGH"
    assert m.judge({"person", "helmet"}, 5)[0] == "MEDIUM"
    assert m.judge({"person", "helmet"}, 40)[0] == "HIGH"  # 얼굴 가림 + 배회
    assert m.judge({"person"}, 40)[0] == "MEDIUM"  # 배회
    assert m.judge({"person", "cardboard box"}, 40)[0] == "LOW"  # 택배 기사는 오래 있어도 배회 아님


def test_sends_every_frame_to_llm():
    sent = []
    m.LLM_URL, real = "http://llm.test", m.send_to_llm
    m.send_to_llm = sent.append
    try:
        for _ in range(3):
            post(202)
        assert [s["frame_no"] for s in sent] == [1, 2, 3] and sent[0]["captured_at"]
    finally:
        m.LLM_URL, m.send_to_llm = None, real


def test_representative_upload():
    calls = []
    real = m.requests.post
    m.requests.post = lambda url, files, timeout: calls.append((url, files)) or SimpleNamespace(
        ok=True, status_code=201, text="", json=lambda: {"mediaId": 1, "eventId": 303})
    m.SPRING_URL = "http://spring.test"
    blank = cv2.imencode(".jpg", np.zeros((480, 640, 3), np.uint8))[1].tobytes()
    try:
        post(303, blank), post(303), post(303, blank)  # 빈 사진 / 사람 4명 / 빈 사진 -> 2번이 대표
        r = client.post("/vision/events/303/representative")
        assert r.status_code == 200 and r.json()["mediaId"] == 1 and r.json()["frame_no"] == 2
        assert calls[0][0] == "http://spring.test/api/v1/events/303/image"
        assert calls[0][1]["file"][1] == BUS.read_bytes()  # 키 file, 그 사진 원본 그대로
        assert client.post("/vision/events/404/representative").status_code == 404
    finally:
        m.requests.post, m.SPRING_URL = real, None


def test_rejects_non_image():
    assert post(1, data=b"not an image").status_code == 400


def test_token():
    m.TOKEN = "secret"
    try:
        assert post(1).status_code == 401
        assert post(1, headers={"Authorization": "Bearer secret"}).status_code == 200
    finally:
        m.TOKEN = None


if __name__ == "__main__":
    for t in (test_person_detected, test_judge_rules, test_sends_every_frame_to_llm, test_representative_upload,
              test_rejects_non_image, test_token):
        t()
    print("OK")
