"""허인혜 LLM 서버 자리를 임시로 대신하는 가짜 수신기. Vision 이 보내는 JSON 을 받아 Event 별 최신값을 보관한다.

실행: uvicorn mock_llm:app --port 8001
Vision 쪽: LLM_URL=http://127.0.0.1:8001/vision/result  (Windows 에서 localhost 는 접속마다 ~2초 지연)
진짜 LLM 서버가 같은 경로로 받으면 Vision 코드는 안 바뀐다.
"""
from fastapi import FastAPI

app = FastAPI(title="mock-llm")
latest: dict[int, dict] = {}


@app.post("/vision/result")
def receive(payload: dict):
    latest[payload["event_id"]] = payload
    print(f"[LLM 수신] event={payload['event_id']} frame={payload['frame_no']} "
          f"{payload['vision_risk_level']} {payload['vision_reasons']}", flush=True)
    return {"ok": True}


@app.get("/vision/result/{event_id}")
def get(event_id: int):
    return latest.get(event_id, {})
