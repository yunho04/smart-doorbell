"""테스트용 가짜 Spring 서버 (포트 8080). 「LLM 연동 API 명세서 MVP v1」의 Spring 쪽 API를 흉내 낸다.

- POST /api/v1/events/{eventId}/response : 중간 대사 수신 (실제 Spring은 MQTT로 Pi B에 전달)
- POST /api/v1/events/{eventId}/result   : 최종 위험도·요약 수신 (실제 Spring은 COMPLETED 처리)
- POST /api/v1/events/{eventId}/finalize-now : (테스트 편의) AI 서버에 finalize를 대신 호출

실행: uvicorn scripts.fake_spring:app --port 8080
"""
import os

import httpx
from fastapi import FastAPI

app = FastAPI(title="Fake Spring")
AI_BASE_URL = os.getenv("AI_BASE_URL", "http://127.0.0.1:8001")
_response_id = 0


@app.post("/api/v1/events/{event_id}/response", status_code=201)
def response(event_id: int, body: dict):
    global _response_id
    _response_id += 1
    print(f"\n[Spring /response] eventId={event_id} {body['responseCode']} \"{body['responseText']}\""
          f"  -> (실제 Spring: event_responses 저장 + MQTT doorbell/1/response 발행)", flush=True)
    return {"responseId": _response_id, "eventId": event_id, **body}


@app.post("/api/v1/events/{event_id}/result")
def result(event_id: int, body: dict):
    print(f"\n[Spring /result] eventId={event_id} riskLevel={body['riskLevel']} summary=\"{body['summary']}\""
          f"  -> (실제 Spring: COMPLETED 처리)", flush=True)
    return {"eventId": event_id, "status": "COMPLETED"}


@app.post("/api/v1/events/{event_id}/finalize-now")
def finalize_now(event_id: int):
    """실제 Spring은 마지막 감지 후 10초 미감지면 자동으로 호출한다."""
    r = httpx.post(f"{AI_BASE_URL}/api/v1/events/{event_id}/finalize", json={"eventId": event_id})
    return {"aiStatus": r.status_code, "aiBody": r.json()}
