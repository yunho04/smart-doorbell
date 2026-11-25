"""평가 세트(data/eval_cases.json)로 위험도 판단 일치율을 잰다 (NFR-04 목표 80%).

  python scripts/eval_rag.py            # RAG 사용 (실제 서비스와 같은 방식)
  python scripts/eval_rag.py --no-rag   # 유사 사례 없이 LLM만
  python scripts/eval_rag.py --compare  # 둘 다 돌려서 비교 (Groq 호출 2배)

최종 위험도 = max(Vision 1차, LLM 판단)  ← analyzer와 같은 규칙
.env가 groq면 실제 Groq를 호출한다 (25건 x 1회). 키가 없으면 규칙 기반(Mock)으로 돈다.
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.config import settings                         # noqa: E402
from app.schemas import EventFeatures                    # noqa: E402
from app.services.analyzer import max_level             # noqa: E402
from app.services.llm import llm                        # noqa: E402
from app.services.rag_store import case_store           # noqa: E402

LEVELS = ["LOW", "MEDIUM", "HIGH"]


def run(use_rag: bool) -> float:
    cases = json.loads((ROOT / "data/eval_cases.json").read_text(encoding="utf-8"))
    print(f"\n== {'RAG 사용' if use_rag else 'RAG 없음'} | {llm.model_name} | 사례 저장소 {len(case_store)}건 ==")
    hit, confusion, fallback, t0 = 0, Counter(), 0, time.perf_counter()
    for c in cases:
        f = EventFeatures(**c["features"])
        examples = case_store.search(f, k=settings.RAG_TOP_K) if use_rag else []
        out = llm.analyze_event(f, c["transcripts"], examples, c["vision_reasons"])
        final = max_level(out["risk_level"], f.vision_risk_level).value
        fallback += out.get("model_name") == "fallback-rule"
        ok = final == c["expected"]
        hit += ok
        confusion[(c["expected"], final)] += 1
        mark = "✓" if ok else "✗"
        print(f"  {mark} {c['eval_id']} {c['memo'][:18]:18} 정답 {c['expected']:6} 판단 {final:6}"
              + ("" if ok else f"  ← {out['reason'][:60]}"))
    acc = hit / len(cases)
    print(f"\n  일치율 {hit}/{len(cases)} = {acc:.0%}  (목표 80%)  {time.perf_counter() - t0:.1f}초"
          + (f"  ※ Groq 실패로 규칙 대체 {fallback}건" if fallback else ""))
    print("  정답\\판단  " + "  ".join(f"{lv:>6}" for lv in LEVELS))
    for e in LEVELS:
        print(f"  {e:8}  " + "  ".join(f"{confusion[(e, p)]:>6}" for p in LEVELS))
    return acc


if __name__ == "__main__":
    if "--compare" in sys.argv:
        a, b = run(False), run(True)
        print(f"\n== 비교: RAG 없음 {a:.0%} → RAG 사용 {b:.0%} ({(b - a) * 100:+.0f}%p)")
    else:
        run("--no-rag" not in sys.argv)
