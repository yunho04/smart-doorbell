"""실행: python test_app.py  (또는 pytest). ultralytics 에 들어 있는 bus.jpg(사람 4명+버스)로 확인."""
import tempfile
from pathlib import Path
from types import SimpleNamespace

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


def test_label_needs_consecutive_frames():
    e = {"streak": m.Counter(), "seen": set()}
    for labels in [{"knife"}, set(), {"knife"}, set(), {"knife"}]:  # 칼이 띄엄띄엄 3장: 오탐으로 봄 (event 8)
        m.confirm(e, labels | {"person"})
    assert "knife" not in e["seen"] and "person" in e["seen"]
    m.confirm(e, {"person", "knife"})  # 바로 앞 사진에도 칼 → 연속 2장
    assert "knife" in e["seen"]
    m.confirm(e, {"person"})
    assert "knife" in e["seen"]  # 한 번 인정되면 유지


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
    calls, v1_only = [], []  # v1_only 에 값이 있으면 가짜 Spring 이 v2 주소에 404 (전환 전)

    def fake_post(url, files, timeout):
        calls.append((url, files))
        missing = v1_only and url.endswith("representative-image")
        return SimpleNamespace(ok=not missing, status_code=404 if missing else 201, text="",
                               json=lambda: {"mediaId": 1, "eventId": 303, "status": "SAVED"})

    real = m.requests.post
    m.requests.post = fake_post
    m.SPRING_URL = "http://spring.test"
    try:
        post(303), post(303)
        r = client.post("/vision/events/303/representative", json={"eventId": 303, "representativeFrameId": 2})  # v2 명세
        assert r.status_code == 200 and r.json()["mediaId"] == 1 and r.json()["frame_no"] == 2
        assert calls[0][0] == "http://spring.test/api/v1/events/303/representative-image"
        assert calls[0][1]["file"][1] == BUS.read_bytes()  # 키 file, 그 사진 원본 그대로
        assert client.post("/vision/events/303/representative", json={"frame_no": 1}).status_code == 200  # 11-18 형식
        v1_only.append(1)
        calls.clear()
        assert client.post("/vision/events/303/representative", json={"frame_no": 1}).status_code == 200
        assert [u.rsplit("/", 1)[1] for u, _ in calls] == ["representative-image", "image"]  # v1 Spring 으로 넘어감
        assert client.post("/vision/events/303/representative", json={"frame_no": 99}).status_code == 404
        assert client.post("/vision/events/303/representative", json={"eventId": 1, "representativeFrameId": 1}).status_code == 400
    finally:
        m.requests.post, m.SPRING_URL = real, None


def test_saves_frames_per_event_folder():
    with tempfile.TemporaryDirectory() as d:
        m.SAVE_DIR = d
        try:
            post(404), post(404)
            [folder] = Path(d).iterdir()
            assert folder.name.startswith("event404_")
            assert sorted(p.name for p in folder.iterdir()) == ["frame0001.jpg", "frame0002.jpg"]
        finally:
            m.SAVE_DIR = None


def test_latest_page_is_localhost_only():
    assert client.get("/vision/latest").status_code == 403  # TestClient 는 localhost 가 아님


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
    for t in (test_person_detected, test_judge_rules, test_label_needs_consecutive_frames, test_sends_every_frame_to_llm, test_representative_upload,
              test_saves_frames_per_event_folder, test_latest_page_is_localhost_only, test_rejects_non_image,
              test_token):
        t()
    print("OK")
