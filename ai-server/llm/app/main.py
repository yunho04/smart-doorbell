"""STT·LLM 서버 진입점.

실행: uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
문서: http://localhost:8001/docs
(Vision 서버가 8000을 쓰므로 LLM 서버는 8001)
"""
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import events, feedback, vision
from app.services.llm import llm
from app.services.pending_store import pending_store
from app.services.rag_store import case_store
from app.services.stt import stt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ai-llm")

app = FastAPI(title="Smart Doorbell STT·LLM Server", version="mvp-v1")

app.include_router(vision.router)
app.include_router(events.router)
app.include_router(feedback.router)


@app.get("/health", tags=["health"])
def health():
    return {
        "status": "ok",
        "stt": stt.name,
        "llm": llm.model_name,
        "rag_cases": len(case_store),
        "pending_feedback": len(pending_store),
        "spring_base_url": settings.SPRING_BASE_URL,
    }


# ---------- 요청 로그 (경로, 상태 코드, 처리 시간) ----------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    start = time.perf_counter()
    response = await call_next(request)
    log.info("%s %s -> %s (%dms)", request.method, request.url.path,
             response.status_code, (time.perf_counter() - start) * 1000)
    return response


# ---------- 에러 형식 통일: {error_code, message} ----------
@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error_code": "INVALID_REQUEST", "message": str(exc.errors())})


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error_code": f"HTTP_{exc.status_code}", "message": str(exc.detail)})


@app.exception_handler(Exception)
async def unknown_error(_: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"error_code": "INTERNAL_ERROR", "message": str(exc)})
