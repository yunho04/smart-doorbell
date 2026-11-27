"""가상 LLM HTTP 서버.

Spring 의 LlmClient 가 호출하는 두 엔드포인트를 받는다.
  POST /api/v1/events/{eventId}/finalize   본문 {"eventId": n}
  POST /api/v1/events/{eventId}/feedback   본문 {"eventId", "summary", "accuracyLevel"}
finalize 를 받으면 즉시 200 을 돌려주고(Spring read timeout 3초), 별도 스레드에서
가상 Vision 대표 이미지 업로드 → POST /api/v1/events/{eventId}/result 순서로 Spring 에 전송한다.
"""
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import vision

ROUTE = re.compile(r"^/api/v1/events/(\d+)/(finalize|feedback)$")


class MockLlm:
    def __init__(self, port, api, result_delay=1.5):
        self.api, self.result_delay = api, result_delay
        self.cond = threading.Condition()
        self.requests = []      # {"kind", "eventId", "body"}
        self.plans = {}         # eventId -> {"result": payload, "image": bytes}
        self.outcomes = {}      # eventId -> {"image": Response, "result": Response} | {"error": str}
        self.unplanned = []     # 시뮬레이터가 만들지 않은 이벤트의 finalize (응답만 하고 무시)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                match = ROUTE.match(self.path)
                if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
                    raw = b""       # Spring RestClient 는 본문을 chunked 로 보낸다
                    while True:
                        size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                        if size == 0:
                            while self.rfile.readline().strip():
                                pass
                            break
                        raw += self.rfile.read(size)
                        self.rfile.readline()
                else:
                    raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                try:
                    body = json.loads(raw or b"null")
                except ValueError:
                    body = {"_raw": raw.decode("utf-8", "replace")}
                if match:
                    owner._received(match.group(2), int(match.group(1)), body)
                payload = json.dumps({"ok": bool(match)}).encode()
                self.send_response(200 if match else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True

    def start(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def plan(self, event_id, result, image):
        with self.cond:
            self.plans[event_id] = {"result": result, "image": image}

    def _received(self, kind, event_id, body):
        with self.cond:
            self.requests.append({"kind": kind, "eventId": event_id, "body": body})
            plan = self.plans.get(event_id) if kind == "finalize" else None
            if kind == "finalize" and plan is None:
                self.unplanned.append(event_id)
            self.cond.notify_all()
        if plan:
            threading.Thread(target=self._finalize, args=(event_id, plan), daemon=True).start()

    def _finalize(self, event_id, plan):
        time.sleep(self.result_delay)   # 분석 시간 흉내 (그 사이 Spring 상태는 ANALYZING)
        try:
            outcome = {"image": vision.upload_representative(self.api, event_id, plan["image"])}
            outcome["result"] = self.api.post_result(event_id, plan["result"])
        except Exception as exc:  # 네트워크 오류도 러너가 FAIL 로 보고할 수 있게 기록
            outcome = {"error": repr(exc)}
        with self.cond:
            self.outcomes[event_id] = outcome
            self.cond.notify_all()

    def _wait(self, find, timeout):
        deadline = time.monotonic() + timeout
        with self.cond:
            while True:
                found = find()
                remaining = deadline - time.monotonic()
                if found is not None or remaining <= 0:
                    return found
                self.cond.wait(remaining)

    def wait_requests(self, kind, event_id, timeout, count=1):
        def find():
            hits = [r for r in self.requests if r["kind"] == kind and r["eventId"] == event_id]
            return hits if len(hits) >= count else None
        return self._wait(find, timeout) or []

    def requests_for(self, kind, event_id):
        with self.cond:
            return [r for r in self.requests if r["kind"] == kind and r["eventId"] == event_id]

    def wait_outcome(self, event_id, timeout):
        return self._wait(lambda: self.outcomes.get(event_id), timeout)
