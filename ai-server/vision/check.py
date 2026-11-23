"""현장 점검: 시연·통합 테스트 전에 한 번 돌린다.  python check.py

내 IP(→ Pi A 설정과 같아야 함), Vision 서버, LLM·Spring 연결을 한 번에 확인한다.
LLM·Spring 주소는 .vscode/tasks.json(Ctrl+Shift+B 설정)에서 읽는다. IP가 바뀌면 거기만 고친다.
"""
import json
import socket
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

TASKS = Path(__file__).parent / ".vscode" / "tasks.json"


def env_from_tasks() -> dict:
    if not TASKS.exists():  # VS Code 설정이 없으면 환경변수에서
        import os
        return {k: os.environ.get(k, "http://127.0.0.1:1") for k in ("LLM_URL", "SPRING_URL")}
    lines = [l for l in TASKS.read_text(encoding="utf-8").splitlines() if not l.strip().startswith("//")]
    return json.loads("\n".join(lines))["tasks"][0]["options"]["env"]


def reachable(url: str) -> bool:
    u = urlparse(url)
    try:
        socket.create_connection((u.hostname, u.port or 80), timeout=2).close()
        return True
    except OSError:
        return False


def my_ip(toward: str) -> str:
    """그 주소로 갈 때 쓰는 내 네트워크 IP (실제로 패킷은 안 보냄)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((urlparse(toward).hostname, 1))
        return s.getsockname()[0]
    finally:
        s.close()


if __name__ == "__main__":
    env = env_from_tasks()
    ip = my_ip(env["SPRING_URL"])
    print(f"내 IP          {ip}  → Pi A config의 vision_base_url 이 http://{ip}:8000 인지 정원님께 확인")
    try:
        h = json.load(urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2))
        print(f"Vision 서버    켜짐 (LLM={h['llm_url']}, Spring={h['spring_url']}, 사진 저장={h['save_dir']})")
    except OSError:
        print("Vision 서버    꺼짐 → VS Code에서 Ctrl+Shift+B")
    for name in ("LLM_URL", "SPRING_URL"):
        print(f"{name:14s} {env[name]}  {'연결됨' if reachable(env[name]) else '연결 안 됨 → 주소·같은 와이파이 확인'}")
