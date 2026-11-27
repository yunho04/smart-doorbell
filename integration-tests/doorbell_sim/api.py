"""Spring REST 호출. 기기/서버 간 호출은 세션 없이, 대시보드 호출은 로그인 세션으로 보낸다."""
import requests

TIMEOUT = 10


class SpringApi:
    def __init__(self, base_url):
        self.base = base_url.rstrip("/")
        self.machine = requests.Session()      # Pi / Vision / LLM 역할 (쿠키 없음)
        self.dashboard = requests.Session()    # React 대시보드 역할 (세션 쿠키)
        self.machine.trust_env = self.dashboard.trust_env = False

    def _url(self, path):
        return self.base + path

    # --- 대시보드(세션) ---
    def login(self, password):
        return self.dashboard.post(self._url("/api/v1/auth/login"), json={"password": password}, timeout=TIMEOUT)

    def list_events(self):
        return self.dashboard.get(self._url("/api/v1/events"), timeout=TIMEOUT)

    def get_event(self, event_id):
        return self.dashboard.get(self._url("/api/v1/events/%d" % event_id), timeout=TIMEOUT)

    def get_image(self, event_id):
        return self.dashboard.get(self._url("/api/v1/events/%d/image" % event_id), timeout=TIMEOUT)

    def send_feedback(self, event_id, accuracy_level):
        return self.dashboard.post(self._url("/api/v1/events/%d/feedback" % event_id),
                                   json={"accuracyLevel": accuracy_level}, timeout=TIMEOUT)

    # --- Vision / LLM (세션 없음) ---
    def upload_representative_image(self, event_id, data, filename, content_type):
        return self.machine.post(self._url("/api/v1/events/%d/representative-image" % event_id),
                                 files={"file": (filename, data, content_type)}, timeout=TIMEOUT)

    def post_result(self, event_id, payload):
        return self.machine.post(self._url("/api/v1/events/%d/result" % event_id), json=payload, timeout=TIMEOUT)

    def post_response(self, event_id, response_code, response_text):
        return self.machine.post(self._url("/api/v1/events/%d/response" % event_id),
                                 json={"responseCode": response_code, "responseText": response_text}, timeout=TIMEOUT)

    def is_up(self):
        try:
            return self.machine.get(self._url("/api/v1/auth/check"), timeout=2).status_code == 200
        except requests.RequestException:
            return False
