"""진입점: 사전 점검 → 시나리오 실행 → 요약. 실패가 있으면 종료 코드 1."""
import argparse
import sys
from urllib.parse import urlsplit

from . import runner
from .api import SpringApi
from .backend import Backend, listener_pid, uses_test_config
from .db import Db
from .llm import MockLlm
from .pi import VirtualPi
from .report import Abort, Reporter
from .scenarios import SCENARIOS
from .settings import BACKEND_PROPS, TEST_PROPS, load_properties, resolve


def parse_args():
    parser = argparse.ArgumentParser(prog="run.sh", description="Smart Doorbell 통합 테스트 시뮬레이터")
    parser.add_argument("--scenario", action="append", choices=list(SCENARIOS), metavar="NAME",
                        help="실행할 시나리오 (여러 번 지정 가능, 기본: 전체). " + ", ".join(SCENARIOS))
    parser.add_argument("--visit-seconds", type=int, default=4, help="방문 중 센서 감지를 보내는 시간(초). 기본 4")
    parser.add_argument("--device-id", type=int, default=1, help="가상 Pi1 의 deviceId. 기본 1")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080", help="Spring 주소")
    parser.add_argument("--password", default=None, help="대시보드 비밀번호 (기본: DOORBELL_PASSWORD 또는 application.properties)")
    parser.add_argument("--keep-backend", action="store_true", help="시뮬레이터가 띄운 백엔드를 끝난 뒤에도 유지")
    parser.add_argument("--no-start-backend", action="store_true", help="백엔드가 꺼져 있어도 자동으로 띄우지 않음")
    parser.add_argument("--allow-foreign-backend", action="store_true",
                        help="테스트 설정으로 뜬 백엔드인지 확인하지 않음 (실제 LLM 으로 요청이 나갈 수 있음)")
    return parser.parse_args()


def main():
    args = parse_args()
    import os
    props, test_props = load_properties(BACKEND_PROPS), load_properties(TEST_PROPS)
    llm_url = urlsplit(test_props["llm.base-url"])
    broker = urlsplit(resolve(props.get("mqtt.broker-url", "tcp://localhost:1883")))
    port = urlsplit(args.base_url).port or 80
    password = args.password or os.environ.get("DOORBELL_PASSWORD") or resolve(props.get("app.auth.password"))

    rep = Reporter()
    api = SpringApi(args.base_url)
    backend = Backend(api, port)
    llm = pi = None
    print("Smart Doorbell 통합 테스트 시뮬레이터")
    print("  Spring %s | MQTT %s:%s | 가상 LLM %s | deviceId %d" % (
        args.base_url, broker.hostname, broker.port or 1883, test_props["llm.base-url"], args.device_id))
    rep.section("사전 점검")
    try:
        try:
            llm = MockLlm(llm_url.port, api)
            llm.start()
            rep.check("가상 LLM 서버 기동", True, "127.0.0.1:%d" % llm_url.port)
        except OSError as exc:
            llm = None
            rep.require("가상 LLM 서버 기동", False, "포트 %d 사용 불가: %s" % (llm_url.port, exc))

        if api.is_up():
            pid = listener_pid(port)
            safe = pid is not None and uses_test_config(pid)
            if args.allow_foreign_backend and not safe:
                rep.skip("백엔드 LLM 주소 격리 확인", "--allow-foreign-backend 지정")
            else:
                rep.require("실행 중인 백엔드가 통합 테스트 설정(가상 LLM)으로 기동됨", safe,
                            "pid=%s" % pid if safe else
                            "포트 %d 의 백엔드가 %s 없이 떠 있어 실제 LLM 으로 요청이 갈 수 있습니다. "
                            "백엔드를 종료한 뒤 다시 실행하세요 (run.sh 가 테스트 설정으로 직접 띄웁니다)." % (port, TEST_PROPS.name))
        elif args.no_start_backend:
            rep.require("백엔드 실행 중", False, "%s 응답 없음" % args.base_url)
        else:
            print("  백엔드를 테스트 설정으로 기동합니다... (로그: %s)" % backend.log_path, flush=True)
            started = backend.start()
            rep.require("백엔드 기동 (가상 LLM 설정 적용)", started,
                        "pid=%s" % listener_pid(port) if started else "기동 실패, 로그 확인: %s" % backend.log_path)

        try:
            pi = VirtualPi(broker.hostname, broker.port or 1883, args.device_id)
            connected = pi.start()
        except OSError as exc:
            connected, pi = False, None
            print("  MQTT 오류: %s" % exc)
        rep.require("MQTT 브로커 연결 및 구독 (doorbell/%d/event, /response)" % args.device_id, connected,
                    "" if connected else "브로커를 먼저 실행하세요: brew services start mosquitto")

        login = api.login(password)
        rep.require("대시보드 로그인 (세션)", login.status_code == 200, "HTTP %s" % login.status_code)

        env = runner.Env(rep, api, pi, llm, Db(props), args.device_id, args.visit_seconds)
        runner.run(env, args.scenario or list(SCENARIOS))
        if llm.unplanned:
            print("\n  참고: 시뮬레이터가 만들지 않은 이벤트의 finalize 를 받아 무시했습니다: %s" % sorted(set(llm.unplanned)))
    except Abort:
        print("  → 사전 점검 실패로 시나리오를 실행하지 않았습니다.")
    except KeyboardInterrupt:
        print("\n중단됨")
    finally:
        if pi:
            pi.stop()
        if backend.process and not args.keep_backend:
            print("\n시뮬레이터가 띄운 백엔드를 종료합니다.")
            backend.stop()
        elif backend.process:
            print("\n백엔드를 유지합니다 (pid=%s, 가상 LLM 설정). 종료: kill %s" % (listener_pid(port), listener_pid(port)))
        if llm:
            llm.stop()
    ok = rep.summary()
    if rep.event_ids:
        print("  대시보드 확인: 백엔드/프론트 실행 후 로그인 → 요약이 '[통합테스트]' 로 시작하는 이벤트")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
