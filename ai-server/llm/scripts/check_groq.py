"""Groq 실제 연결 확인 (키가 .env에 들어 있어야 함). 서버를 켜지 않고 실행한다.

  python scripts/check_groq.py                 # LLM 확인 (방문 목적 4문장 + 최종 분석 2건)
  python scripts/check_groq.py 녹음파일.m4a      # + STT 확인 (내 목소리로 녹음한 파일)
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings                      # noqa: E402
from app.schemas import EventFeatures, Purpose       # noqa: E402
from app.services.llm import llm                     # noqa: E402
from app.services.stt import stt                     # noqa: E402

if not settings.GROQ_API_KEY:
    sys.exit("GROQ_API_KEY가 비어 있어요. ai-server/llm/.env에 키를 넣고 다시 실행하세요.")
print(f"LLM: {llm.model_name} (빠른 모델 {settings.LLM_FAST_MODEL}) / STT: {stt.name}\n")

print("== 1. 방문 목적 분류")
for text in ["택배 왔습니다", "가스 점검 나왔습니다", "집에 아무도 없어요? 알림 보내지 마", "음... 어..."]:
    t0 = time.perf_counter()
    purpose, conf = llm.classify_purpose(text)
    print(f"  {text!r:38} -> {purpose.value:8} {conf:.2f}  ({(time.perf_counter() - t0) * 1000:.0f}ms)")

print("\n== 2. 최종 위험도 + 요약")
cases = [
    ("낮 택배", EventFeatures(hour=14, stay_sec=20, doorbell_pressed=True, package_detected=True,
                             purpose=Purpose.DELIVERY, purpose_confidence=0.9), ["택배 왔습니다"], ["택배 상자 보임"]),
    ("새벽 수상", EventFeatures(hour=3, stay_sec=150, face_covered=True, vision_risk_level="MEDIUM"),
     ["집에 아무도 없어요? 알림 보내지 마"], ["얼굴 가림: helmet", "150초 머묾"]),
]
for name, feat, said, vision in cases:
    t0 = time.perf_counter()
    out = llm.analyze_event(feat, said, [], vision)
    print(f"  [{name}] {out['risk_level'].value} ({out['model_name']}, {(time.perf_counter() - t0) * 1000:.0f}ms)")
    print(f"     근거: {out['reason']}\n     요약: {out['summary']}")

if len(sys.argv) > 1:
    print("\n== 3. STT")
    t0 = time.perf_counter()
    text, conf = stt.transcribe(Path(sys.argv[1]))
    print(f"  {text!r} (신뢰도 {conf}, {(time.perf_counter() - t0) * 1000:.0f}ms)")
