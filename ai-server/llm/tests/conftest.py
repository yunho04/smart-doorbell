import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 테스트가 실제 사례 파일과 음성 폴더를 건드리지 않도록 임시 경로 사용
_tmp = Path(tempfile.mkdtemp())
shutil.copy(ROOT / "data/cases.json", _tmp / "cases.json")
os.environ["CASES_PATH"] = str(_tmp / "cases.json")
os.environ["AUDIO_DIR"] = str(_tmp / "audio")
os.environ["PENDING_PATH"] = str(_tmp / "pending_features.json")

# MVP v1처럼 인증 없이 테스트 (인증 테스트는 개별로 켬)
os.environ["DEVICE_KEYS"] = ""
os.environ["INTERNAL_TOKEN"] = ""
os.environ["SPRING_BASE_URL"] = "http://spring.test:8080"
os.environ["VISION_BASE_URL"] = "http://vision.test:8000"
os.environ["SEND_RESPONSE_TO_SPRING"] = "false"
# 테스트는 항상 Mock으로 (실제 Groq 호출·과금 방지). Groq 코드는 test_groq.py에서 가짜 클라이언트로 검사
os.environ["STT_BACKEND"] = "mock"
os.environ["LLM_BACKEND"] = "mock"
os.environ["GROQ_API_KEY"] = ""
