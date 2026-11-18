"""스마트 도어벨 Vision 서버 (장준용).

Pi가 방문 Event 동안 사진을 1초에 1장씩 보낸다 -> 장마다 물체를 찾고 Event 단위로 모아 1차 위험도를 매긴다
-> 장마다 frame_no·captured_at 을 붙여 LLM 서버로 보낸다. LLM이 Vision 판단 + 다른 센서로 2차 판단 (SAD 3.1 구성도: Vision -> LLM).
Event 가 끝나면 LLM(허인혜)이 고른 frame_no 사진 1장을 Spring 에 대표 사진으로 올린다 (11-17 톡방, 11-18 체크리스트 15단계).
실행: uvicorn app:app --host 0.0.0.0 --port 8000
"""
import base64
import json
import logging
import os
import secrets
import time
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import requests  # ultralytics 가 이미 깔아 둠 (multipart 업로드용)
from fastapi import BackgroundTasks, Body, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from ultralytics import YOLOE

# 찾을 물체(글로 지정)와 라벨별 신뢰도 하한. 11-16 Wikimedia 사진 16장으로 잡은 값, 현관 카메라 사진으로 다시 조정
CLASSES = {"person": 0.4, "helmet": 0.5, "face mask": 0.5, "balaclava": 0.35,
           "cardboard box": 0.4, "knife": 0.3, "baseball bat": 0.5}
FACE_COVER = {"helmet", "face mask", "balaclava"}
WEAPONS = {"knife", "baseball bat"}
MIN_FRAMES = 2  # 라벨이 이 장수 이상 나와야 Event 에 반영 (한 장짜리 오탐 거르기)
LOITER_SEC = 30  # 사람이 이 시간 넘게 보이면 배회
EVENT_TTL = 600  # 이 시간 동안 사진이 안 오면 Event 상태 삭제
KEEP_FRAMES = 300  # Event 당 메모리에 남길 사진 수 (대표 사진 업로드용, 1초 1장이면 최근 5분)
MODEL = os.getenv("VISION_MODEL", "yoloe-26m-seg.pt")  # 서버가 느리면 yoloe-26s-seg.pt (장당 0.6초 -> 0.25초)
LLM_URL = os.getenv("LLM_URL")  # 허인혜 LLM 서버 주소. 비우면 안 보냄
SPRING_URL = os.getenv("SPRING_URL")  # 최윤호 Spring 주소 (예: http://10.21.33.82:8080). 대표 사진 업로드용
SAVE_DIR = os.getenv("SAVE_DIR")  # 설정하면 사진을 Event 폴더별 파일로 저장 (테스트용). 방문자 사진이라 기본은 저장 안 함 (SAD 6)
TOKEN = os.getenv("VISION_API_TOKEN")  # SAD 6.1 장치 키. 비우면 검사 안 함 (로컬 연동 테스트용)
MAX_BYTES = 10 * 1024 * 1024

model = YOLOE(MODEL)
model.set_classes(list(CLASSES))
model.predict(np.zeros((480, 640, 3), np.uint8), verbose=False)  # warm-up: 첫 요청만 느려지는 것 방지
app = FastAPI(title="doorbell-vision")
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("vision")
logging.getLogger("uvicorn.access").addFilter(lambda r: "/vision/latest" not in r.getMessage())  # 1초 새로고침 줄은 숨김
events: dict[int, dict] = {}  # ponytail: 메모리에만 둠. 서버 재시작하면 진행 중이던 Event 누적값이 사라짐


def log_json(event_id, stage, ms, result, error=None):
    """SAD 8장 로그 형식: JSON 한 줄 (시각, 서비스, event_id, 단계, 처리 시간, 결과, 에러 코드)."""
    log.info(json.dumps({"ts": datetime.now().astimezone().isoformat(timespec="seconds"), "service": "vision",
                         "event_id": event_id, "stage": stage, "elapsed_ms": ms, "result": result, "error": error},
                        ensure_ascii=False))


def judge(seen: set[str], visible_sec: int) -> tuple[str, list[str]]:
    """Event 에서 확인된 라벨 + 머문 시간 -> 1차 위험도(LOW/MEDIUM/HIGH)와 근거."""
    weapons, covers, package = seen & WEAPONS, seen & FACE_COVER, "cardboard box" in seen
    loiter = visible_sec >= LOITER_SEC and not package  # 택배 상자가 보이면 오래 있어도 배회로 안 봄
    reasons = []
    if weapons:
        reasons.append("흉기 의심: " + ", ".join(sorted(weapons)))
    if covers:
        reasons.append("얼굴 가림: " + ", ".join(sorted(covers)))
    if loiter:
        reasons.append(f"{visible_sec}초 머묾")
    if package:
        reasons.append("택배 상자 보임")
    level = "HIGH" if weapons or (covers and loiter) else "MEDIUM" if covers or loiter else "LOW"
    return level, reasons


def check_token(authorization: str | None):
    if TOKEN and not secrets.compare_digest((authorization or "").encode(), f"Bearer {TOKEN}".encode()):
        raise HTTPException(401, "invalid token")


def send_to_llm(payload: dict):
    req = urllib.request.Request(LLM_URL, json.dumps(payload, ensure_ascii=False).encode(),
                                 {"Content-Type": "application/json"})
    t0, error = time.perf_counter(), None
    try:
        urllib.request.urlopen(req, timeout=3).close()
    except Exception as ex:  # LLM 서버가 죽어도 Vision 은 계속 돈다
        error = type(ex).__name__
    log_json(payload["event_id"], "vision_to_llm", round((time.perf_counter() - t0) * 1000),
             payload["vision_risk_level"], error)


# ponytail: async 안에서 predict 를 바로 돌려 요청이 한 줄로 처리됨. Pi 1대(1초 1장)엔 충분, 여러 대면 워커 늘리기
@app.post("/vision/analyze")
async def analyze(
    background: BackgroundTasks,
    image: UploadFile = File(...),
    event_id: int = Form(...),
    authorization: str | None = Header(None),
):
    check_token(authorization)
    data = await image.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "image too large")
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(400, "not an image")

    t0 = time.perf_counter()
    boxes = model.predict(frame, conf=min(CLASSES.values()), verbose=False)[0].boxes
    ms = round((time.perf_counter() - t0) * 1000)
    objects = [
        {"label": model.names[int(c)], "confidence": round(float(p), 3), "bbox": [round(v) for v in xyxy]}
        for c, p, xyxy in zip(boxes.cls, boxes.conf, boxes.xyxy.tolist())
        if p >= CLASSES[model.names[int(c)]]
    ]
    persons = sum(o["label"] == "person" for o in objects)

    now = time.time()
    for k in [k for k, e in events.items() if now - e["updated"] > EVENT_TTL]:
        del events[k]
    e = events.setdefault(event_id, {"frames": 0, "counts": Counter(), "first": None, "last": None, "jpeg": {},
                                     "dir": None})
    e["frames"] += 1
    e["updated"] = now
    if SAVE_DIR:  # 폴더 이름 = eventId + 첫 사진 받은 시각, 파일 이름 = frame_no
        if e["dir"] is None:
            e["dir"] = Path(SAVE_DIR) / f"event{event_id}_{datetime.now():%Y%m%d-%H%M%S}"
            e["dir"].mkdir(parents=True, exist_ok=True)
        (e["dir"] / f"frame{e['frames']:04d}.jpg").write_bytes(data)
    e["jpeg"][e["frames"]] = data  # ponytail: 메모리 보관. Event 당 KEEP_FRAMES 장 넘으면 오래된 것부터 버림
    if len(e["jpeg"]) > KEEP_FRAMES:
        e["jpeg"].pop(next(iter(e["jpeg"])))
    e["counts"].update({o["label"] for o in objects})
    if persons:
        e["first"] = e["first"] or now
        e["last"] = now
    visible_sec = round(e["last"] - e["first"]) if e["first"] else 0
    seen = {k for k, n in e["counts"].items() if n >= MIN_FRAMES}
    level, reasons = judge(seen, visible_sec)

    result = {
        "event_id": event_id,
        "frame_no": e["frames"],  # LLM 이 대표 사진 고를 때 쓰는 번호 (11-17 톡방 frameId)
        "captured_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),  # Vision 이 받은 시각
        # 이번 사진 (ERD VISION_RESULTS 컬럼 이름)
        "person_detected": persons > 0,
        "person_count": persons,
        "objects": objects,  # [{label, confidence, bbox:[x1,y1,x2,y2] 픽셀}]
        "processing_ms": ms,
        # Event 누적 (사진 MIN_FRAMES 장 이상에서 확인된 것만)
        "person_visible_sec": visible_sec,
        "package_detected": "cardboard box" in seen,
        "face_covered": bool(seen & FACE_COVER),
        "weapon_labels": sorted(seen & WEAPONS),
        "vision_risk_level": level,
        "vision_reasons": reasons,
    }
    e["result"] = result
    log_json(event_id, "vision_analyze", ms, f"frame={e['frames']} person={persons} risk={level}")

    if LLM_URL:  # 11-17 톡방: 매초 보냄
        background.add_task(send_to_llm, result)
    return result


@app.get("/vision/latest", response_class=HTMLResponse)
def latest(request: Request):
    """마지막으로 받은 사진 + 판단을 1초마다 새로고침해서 보여 준다. 방문자 사진이라 내 PC(localhost)에서만 (SAD 6)."""
    if request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "localhost only")
    page = '<meta http-equiv="refresh" content="1">'
    if not events:
        return page + "아직 받은 사진 없음"
    event_id, e = max(events.items(), key=lambda kv: kv[1]["updated"])
    r, img = e["result"], base64.b64encode(e["jpeg"][e["frames"]]).decode()
    labels = ", ".join(sorted({o["label"] for o in r["objects"]})) or "없음"
    return (page + f"<p>event {event_id} · frame {r['frame_no']} · {r['captured_at']} · <b>{r['vision_risk_level']}</b>"
            f" · 이번 사진: {labels} · 근거: {', '.join(r['vision_reasons']) or '없음'}</p>"
            f'<img src="data:image/jpeg;base64,{img}" style="max-width:100%">')


@app.post("/vision/events/{event_id}/representative")
def representative(event_id: int, frame_no: int = Body(..., embed=True), authorization: str | None = Header(None)):
    """LLM 이 finalize 뒤 고른 frame_no 사진 1장을 Spring POST /api/v1/events/{id}/image (multipart 키 file) 로 올린다."""
    check_token(authorization)
    jpeg = events.get(event_id, {}).get("jpeg", {}).get(frame_no)
    if jpeg is None:
        raise HTTPException(404, "no such frame")
    if not SPRING_URL:
        raise HTTPException(503, "SPRING_URL not set")
    t0, url = time.perf_counter(), f"{SPRING_URL.rstrip('/')}/api/v1/events/{event_id}/image"
    try:
        r = requests.post(url, files={"file": (f"event{event_id}_frame{frame_no}.jpg", jpeg, "image/jpeg")}, timeout=5)
    except requests.RequestException as ex:
        log_json(event_id, "vision_to_spring_image", round((time.perf_counter() - t0) * 1000), None, type(ex).__name__)
        raise HTTPException(502, f"spring unreachable: {type(ex).__name__}")
    log_json(event_id, "vision_to_spring_image", round((time.perf_counter() - t0) * 1000),
             f"frame={frame_no} status={r.status_code}", None if r.ok else r.status_code)
    if not r.ok:
        raise HTTPException(502, f"spring {r.status_code}: {r.text[:200]}")
    return {**r.json(), "frame_no": frame_no}
