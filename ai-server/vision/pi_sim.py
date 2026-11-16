"""Pi 흉내: 사진 한 장을 1초에 1장씩 Vision 서버로 보낸다 (이정원 Pi 코드 참고용).

사용: python pi_sim.py <사진> <event_id> [보낼 초=10] [url=http://127.0.0.1:8000/vision/analyze]
"""
import sys
import time

import requests

img, event_id = sys.argv[1], sys.argv[2]
seconds = int(sys.argv[3]) if len(sys.argv) > 3 else 10
url = sys.argv[4] if len(sys.argv) > 4 else "http://127.0.0.1:8000/vision/analyze"
data = open(img, "rb").read()

for _ in range(seconds):
    t0 = time.time()
    r = requests.post(url, data={"event_id": event_id}, files={"image": ("frame.jpg", data, "image/jpeg")}, timeout=10)
    j = r.json()
    print(f"[Pi] frame={j['frame_no']} 사람={j['person_count']} {j['processing_ms']}ms "
          f"-> {j['vision_risk_level']} {j['vision_reasons']}", flush=True)
    time.sleep(max(0.0, 1 - (time.time() - t0)))  # 1초에 1장
