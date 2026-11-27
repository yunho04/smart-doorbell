"""경로와 properties 파일 읽기."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # integration-tests/
REPO = ROOT.parent
BACKEND_DIR = REPO / "backend"
BACKEND_PROPS = BACKEND_DIR / "src/main/resources/application.properties"
TEST_PROPS = ROOT / "config/application-integration.properties"
LOG_DIR = ROOT / "logs"                              # logs/ 는 루트 .gitignore 에 이미 포함


def load_properties(path):
    props = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "!")) and "=" in line:
            key, value = line.split("=", 1)
            props[key.strip()] = value.strip()
    return props


def resolve(value):
    """Spring 의 ${ENV:default} 표기를 실제 값으로 바꾼다."""
    return re.sub(r"\$\{([^:}]+):?([^}]*)\}",
                  lambda m: os.environ.get(m.group(1), m.group(2)), value or "")
