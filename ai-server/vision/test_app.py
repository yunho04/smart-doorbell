"""실행: python test_app.py  (또는 pytest). ultralytics 에 들어 있는 bus.jpg(사람 4명+버스)로 확인."""
from pathlib import Path

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


def test_sends_to_llm_only_on_change():
    sent = []
    m.LLM_URL, real = "http://llm.test", m.send_to_llm
    m.send_to_llm = sent.append
    try:
        for _ in range(4):  # 1장: 아직 없음, 2장: person 확인(MIN_FRAMES=2), 3·4장: 변화 없음
            post(202)
        assert len(sent) == 2 and sent[-1]["frame_no"] == 2
    finally:
        m.LLM_URL, m.send_to_llm = None, real


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
    for t in (test_person_detected, test_judge_rules, test_sends_to_llm_only_on_change, test_rejects_non_image,
              test_token):
        t()
    print("OK")
